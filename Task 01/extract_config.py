import argparse
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path 

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

log = logging.getLogger("extract_config")

# Column headings that will appear in the Excel
COLUMNS = ["Main Interface", "Description", "VRF", "Vendor"]

# Vendor fingerprints for cisco configuration files
CISCO_SIGNATURES = [
    (re.compile(r"^\S+#\s*show\s+running-config", re.I | re.M),5),
    (re.compile(r"^Building configuration", re.I | re.M),3),
    (re.compile(r"^\s*vrf definition\s+\S+", re.I | re.M),2),
    (re.compile(r"^\s*vrf forwarding\s+\S+", re.I | re.M),2),
    (re.compile(r"^\s*hostname\s+\S+", re.I | re.M),1),
    (re.compile(r"^\s*end\s*$", re.I | re.M),1)
]

# Vendor fingerprints for huawei configuration files
HUAWEI_SIGNATURES = [
    (re.compile(r"[<\[]\S+[>\]]\s*display\s+current-configuration", re.I | re.M),5),
    (re.compile(r"^<[^<>\s]+>", re.M),3),
    (re.compile(r"^\[[^\[\]\s]+\]", re.M),3),
    (re.compile(r"^\s*ip vpn-instance\s+\S+", re.I | re.M),2),
    (re.compile(r"^\s*ip binding vpn-instance\s+\S+", re.I | re.M),2),
    (re.compile(r"^\s*sysname\s+\S+", re.I | re.M),1),
    (re.compile(r"^\s*return\s*$", re.I | re.M),1)
]



# per-vendor syntax (as Cisco and Huawei write the vrf line in different ways)
@dataclass(frozen=True)
class Syntax:
    vrf: re.Pattern

SYNTAX = {
    "Cisco": Syntax(vrf=re.compile(r"^\s*(?:ip\s+)?vrf\s+forwarding\s+(\S+)", re.I)),
    "Huawei": Syntax(vrf=re.compile(r"^\s*ip\s+binding\s+vpn-instance\s+(\S+)", re.I))
}

# Match and capture the interface name
INTERFACE_RE = re.compile(r"^interface\s+(\S+)\s*$", re.I)
# Match and capture the text after "description"
DESCRIPTION_RE =re.compile(r"^\s*description\s+(.*\S)\s*$", re.I)


## Function to descide whether a file is Cisco or Huawei
def detectVendor(text: str) -> str:
    cisco = sum(w for rx, w in CISCO_SIGNATURES if rx.search(text))    # points for cisco clues in the file
    huawei = sum(w for rx, w in HUAWEI_SIGNATURES if rx.search(text))  # points for huawei clues in the file
    log.debug("vendor scores: cisco=%d huawei=%d", cisco, huawei)      # show the score whenonly running with -v
    if cisco == huawei:
        return "Unknown"  
    return "Cisco" if cisco > huawei else "Huawei"


## Function to read the config file line by line and collect interface details
def parseInterfaces(text: str, vendor: str, subinterfaces_only: bool = True):
    vrf_re = SYNTAX[vendor].vrf
    current = None

    # decide whether a finished interface block should be kept
    def finish(block):
        if not block:
            return None
        if subinterfaces_only and "." not in block["name"]:
            return None
        return block["name"], block["description"], block["vrf"]

    for raw in text.splitlines():
        line = raw.rstrip()
        m = INTERFACE_RE.match(line.strip())  # detect is a line line is "interface ...." line
        if m:
            done = finish(current)            # save the previous before new interface begins
            if done:
                yield done
            current = {"name": m.group(1), "description": "", "vrf": ""}  # start a new record for the new interface
            continue
        # if not inside an interface block, ignore the line
        if current is None:
            continue
        # End of the interface block (interface block is over)
        if line.strip()=="!" or line.strip().lower() in {"end", "return"}:
            done = finish(current)
            if done:
                yield done
            current = None
            continue
        # inside an interface block, look for the description line
        if (d := DESCRIPTION_RE.match(line)):
            current["description"] = d.group(1)
        # or look for the VRF line
        elif (v := vrf_re.match(line)):
            current["vrf"] = v.group(1)
    # end of file
    done = finish(current)
    if done:
        yield done


## Function to process a file
def processFile(path: Path, subinterfaces_only: bool = True) -> list:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.error("Cannot read %s: %s", path, exc)
        return[]

    # skip empty files
    if not text.strip():
        log.warning("%s is empty - Skipped", path)
        return[]

    # detect the vendor. if can't identify, skip 
    vendor = detectVendor(text)
    if vendor == "Unknown":
        log.warning("%s: Vendor can't determine - Skipped", path)
        return[]

    # build a row per interface
    rows = [
        (name, desc, vrf, vendor)
        for name, desc, vrf in parseInterfaces(text, vendor, subinterfaces_only)
    ]

    if not rows:
        log.warning("%s: Detected %s but no matching interfaces are found", path, vendor)
    else:
        log.info("%s: %s, %d interface(s)", path, vendor, len(rows))
    return rows


## Function to write the excel file
def writeExcel(rows: list, outputPath: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Service Details"
    ws.append(COLUMNS)
    for row in rows:
        ws.append(list(row))
    headerFill = PatternFill("solid", fgColor="00B050")
    for cell in ws[1]:
        cell.font = Font(name="Arial", bold=True, color="FFFFFF")
        cell.fill = headerFill
        cell.alignment = Alignment(horizontal="center")
    for r in ws.iter_rows(min_row=2):
        for cell in r:
            cell.font = Font(name="Arial")
    for i, col in enumerate(COLUMNS,1):
        width = max(len(col), *(len(str(r[i-1])) for r in rows)) if rows else len(col)
        ws.column_dimensions[get_column_letter(i)].width = width + 4
    ws.freeze_panes = "A2"
    outputPath.parent.mkdir(parents=True, exist_ok=True)
    wb.save(outputPath)


## Main
def main(argv=None)->int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path, help="router configuration text files")
    ap.add_argument("-o", "--output", type=Path, default=Path("Output/service_details.xlsx"))
    ap.add_argument("--all-interfaces", action="store_true", help="include main interfaces, not only sub-intefaces")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s: %(message)s")

    # process every input file and collect rows
    rows=[]
    for f in args.files:
        rows.extend(processFile(f, not args.all_interfaces))
    # save everything to excel
    writeExcel(rows, args.output)
    log.info("Wrote %d record(s) to %s", len(rows), args.output)
    return 0 


# run main only when executing file
if __name__ == "__main__":
    sys.exit(main())