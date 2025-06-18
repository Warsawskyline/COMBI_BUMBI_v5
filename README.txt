Combustion Parameters Analyzer (COMBI_BUMBI_v5)
===============================================

A comprehensive GUI application for analyzing combustion parameters of various fuels using Cantera. It generates 3D surfaces and contour plots of key combustion parameters and creates a comprehensive PDF report with the results.

Supported Fuels
---------------
- Hydrogen (H2)
- Methane (CH4)
- Carbon Monoxide (CO)
- Methanol (CH3OH) [simplified]
- Acetylene (C2H2)
- Ethylene (C2H4)
- Ethane (C2H6)
- Ammonia (NH3) [simplified]
- Propane (C3H8)

Supported Oxidizers
-------------------
- Air (21% O₂, 79% N₂)
- Oxygen (100% O₂)
- Oxygen-Enriched Air (30% O₂)

Requirements
------------
- Python 3.7 or higher
- Required Python packages:
  - cantera >= 2.6.0
  - numpy >= 1.20.0
  - plotly >= 5.5.0
  - matplotlib >= 3.4.0
  - tkinter (usually included with Python)
  - fpdf2 >= 1.7.6
  - Pillow >= 9.0.0
  - kaleido (for plot export)

Installation
------------
1. **Install Python**:
   Download Python 3.7+ from https://www.python.org/downloads/
   Ensure "Add Python to PATH" is checked during installation

2. **Install Required Packages**:
   Open Command Prompt/Terminal and run: pip install cantera numpy plotly matplotlib fpdf2 Pillow kaleido

Running the Application
-----------------------
1. Save `COMBI_BUMBI_v5.py` to your computer
2. Open Command Prompt/Terminal, navigate to the file directory
3. Run: python COMBI_BUMBI_v5.py


Program Usage
-------------
1. **Input Parameters**:
- Select fuel type from dropdown
- Choose oxidizer from dropdown
- Enter initial temperature [K] (300-1500)
- Enter pressure [atm] (0.5-50)
- Enter equivalence ratio (φ) (0.3-4.0)
- Select grid size (NxN resolution)

2. **Advanced Settings**:
- Access via "Advanced Settings" button
- Configure simulation parameters:
  * Ignition detection method (max_dTdt/max_species)
  * Ignition detection species (OH/H/O/CO/CH₂O)
  * Flame width (spatial domain for flame calculations)
  * Simulation end time for ignition detection
  * Temperature threshold for ignition
- Detailed explanations available via "More Info" buttons

3. **Threshold Settings**:
- Configure outlier compensation parameters
- Set thresholds and multipliers for each combustion parameter

4. Click "Run Calculation" to start analysis
5. Monitor progress via status bar and progress indicator
6. Results are saved in automatically created directory with:
- Interactive HTML plots
- PNG images of all visualizations
- Comprehensive PDF report

Key Features
------------
- Multi-fuel and multi-oxidizer support
- 3D surface visualizations (HTML + PNG)
- Contour plots with fuel-specific colormaps
- Advanced simulation parameter configuration
- Outlier compensation with adjustable thresholds
- Automatic PDF report generation
- Unique results directory for each run
- Progress tracking with time estimation
- Detailed error logging

Results Include
---------------
- Adiabatic flame temperature
- Ignition delay time
- Laminar flame speed
- NOx emissions
- CO and CO₂ emissions (carbon-based fuels)
- Simulation settings summary
- Compensation records
- Physical realism notes

Notes
-----
- Calculations may take several minutes (longer for complex fuels)
- Carbon-based fuels require more computation time than hydrogen
- Use smaller grid sizes (3x3) for faster initial results
- Extreme conditions may produce non-physical results
- PDF report includes important interpretation guidelines
- Detailed parameter explanations available in "More Info" tooltips