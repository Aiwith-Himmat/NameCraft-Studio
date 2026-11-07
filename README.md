# NamePrint Studio 

A reusable Python + Streamlit browser app for printing attendee names on card/badge designs.


## Folder structure
```text
NamePrint_Studio/
├── app.py
├── requirements.txt
└── README.md
```

## Windows setup
Open this folder in VS Code. In PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

If PowerShell blocks activation:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
```

The app opens in your browser at `http://localhost:8501`.

## Input files
- Card template: PNG/JPG. Prefer the clean version with ATTENDEE removed.
- Names list: CSV or Excel. Select the column containing names in the app.

## CCD starting settings
Defaults are tuned as a starting point:
- Uppercase: ON
- Italic: ON
- Rotation: -11 degrees
- White text
- Outline: ON (thin)
- Shadow: ON (subtle)

The exact original font cannot be identified reliably from a flattened image. For an exact match, upload the designer's original TTF/OTF font file. Adjust position and size using preview before generating the full batch.


## V3 layout update
The editor now uses a two-column workspace: all styling controls are grouped on the left, while the live card preview stays in a sticky right-hand panel on desktop. Controls are grouped into expandable sections to reduce page length. The preview refreshes automatically after each setting change.
