# Network Automation Internship-Evaluation Assignment

## Structure
```
Task 01/
├── extract_config.py        # Config parser + vendor detection + Excel export
├── Samples/
│   ├── router_a.txt         # Cisco sample config
│   └── router_b.txt         # Huawei sample config
└── Output/
    └── service_details.xlsx # Generated Excel output
Task 02/
└── Sample Prompt.md   # ISP Network Troubleshooting AI Agent prompt
requirements.txt
README.md
```

## Task 01 – Configuration Data Extraction

### Setup and run (Windows PowerShell)
```powershell
cd "Task 01"
python -m venv ..\.venv                # first time only
..\.venv\Scripts\Activate.ps1
pip install -r ..\requirements.txt     # first time only
python extract_config.py Samples\router_a.txt Samples\router_b.txt -o Output\service_details.xlsx
```

Optional flags: `--all-interfaces` (include main interfaces, not only sub-interfaces) and `-v` (debug logging).

### How vendor detection works
Each file is scored against vendor-specific fingerprints, and the higher score wins.

| | Cisco | Huawei |
|---|---|---|
| Prompt / command | `HOST#show running-config` | `<HOST>display current-configuration` |
| VRF syntax | `vrf definition`, `vrf forwarding` | `ip vpn-instance`, `ip binding vpn-instance` |
| Other keywords | `hostname`, `Building configuration`, `end` | `sysname`, `return` |

If there is no evidence or the scores tie, the vendor is "Unknown" and the file is skipped with a warning.

### Assumptions
- Each input file contains the config of a single device.
- Only sub-interfaces (names containing `.`) are extracted by default.
- A missing description or VRF is left as an empty cell.
- Empty, missing or unreadable files are logged and skipped without crashing.

## Task 02 – Prompt Engineering
The agent prompt is in `Task 02/Sample Prompt.md`. It covers role, scope, protocol expertise, Cisco/Huawei commands, a troubleshooting methodology, safety rules, an output format and worked examples.