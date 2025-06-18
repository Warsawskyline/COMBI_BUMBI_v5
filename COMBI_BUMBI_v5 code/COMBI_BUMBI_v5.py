import cantera as ct
import numpy as np
import plotly.graph_objects as go
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import time
import os
import re
import warnings
import tkinter as tk
from tkinter import ttk, messagebox
from fpdf import FPDF
from PIL import Image
import io
import plotly.io as pio
import sys
import tempfile
import logging

# Dynamic FPDF import handling
try:
    from fpdf.enums import XPos, YPos
    FPDF_NEW_API = True
except ImportError:
    FPDF_NEW_API = False

# Ignore Cantera warnings
warnings.filterwarnings("ignore", module="cantera")

# Color definitions for visualizations
FLAME_COLORS = LinearSegmentedColormap.from_list('flame', ['#000000', '#800000', '#FF0000', '#FFA500', '#FFFF00'])
NOX_COLORS = LinearSegmentedColormap.from_list('nox', ['#00FF00', '#FFFF00', '#FFA500', '#FF0000'])
CO_COLORS = LinearSegmentedColormap.from_list('co', ['#FFFFFF', '#FF0000'])
CO2_COLORS = LinearSegmentedColormap.from_list('co2', ['#FFFFFF', '#00FF00'])

# Fuel definitions with chemical formulas
FUELS = {
    "Hydrogen (H2)": {
        "mechanism": "h2o2.yaml",  # Standardowy mechanizm dla H2/O2
        "formula": "H2:1.0",
        "has_carbon": False
    },

    "Methane (CH4)": {
        "mechanism": "gri30.yaml", # GRI-Mech jest standardem dla metanu
        "formula": "CH4:1.0",
        "has_carbon": True
    },
    "Carbon Monoxide (CO)": {
        "mechanism": "gri30.yaml", # GRI-Mech zawiera reakcje CO
        "formula": "CO:1.0",
        "has_carbon": True
    },
    "Methanol (CH3OH) [simplified]": {
        "mechanism": "gri30.yaml", # GRI-Mech może być używany, choć dla metanolu często są specyficzne mechanizmy (np. DRM)
        "formula": "CH3OH:1.0",
        "has_carbon": True
    },
    "Acetylene (C2H2)": { # Już był, ale upewniamy się, że jest poprawny
        "mechanism": "gri30.yaml",
        "formula": "C2H2:1.0",
        "has_carbon": True
    },
    "Ethylene (C2H4)": {
        "mechanism": "gri30.yaml", # GRI-Mech dla etylenu
        "formula": "C2H4:1.0",
        "has_carbon": True
    },
    "Ethane (C2H6)": { # Już był, ale upewniamy się, że jest poprawny
        "mechanism": "gri30.yaml",
        "formula": "C2H6:1.0",
        "has_carbon": True
    },
    "Ammonia (NH3) [simplified]": {
        "mechanism": "gri30.yaml", # GRI-Mech może nie być idealny dla NH3, lepsze są specyficzne mechanizmy NH3
                                   # Należy znaleźć mechanizm do spalania amoniaku (np. "ammonia.yaml" jeśli istnieje)
                                   # lub rozszerzyć istniejący o reakcje azotu.
        "formula": "NH3:1.0",
        "has_carbon": False
    },
    "Propane (C3H8)": { 
        "mechanism": "gri30.yaml",
        "formula": "C3H8:1.0",
        "has_carbon": True
    }
}

#słownik utleniaczy
OXIDIZERS = {
    "Air": "O2:0.21,N2:0.79",
    "Oxygen (O2)": "O2:1.0",
    "Oxygen-Enriched Air (30% O2)": "O2:0.30,N2:0.70"
}

# Default thresholds and multipliers for outlier compensation
DEFAULT_THRESHOLDS = {
    'T_ad': {'threshold': 3500, 'multiplier': 3, 'unit': 'K'},
    'ignition_delay': {'threshold': 100000, 'multiplier': 3, 'unit': 'μs'}, # (0.1 s)
    'flame_speed': {'threshold': 100, 'multiplier': 3, 'unit': 'm/s'},
    'NOx': {'threshold': 5000, 'multiplier': 3, 'unit': 'ppm'},
    'CO': {'threshold': 50000, 'multiplier': 3, 'unit': 'ppm'},
    'CO2': {'threshold': 200000, 'multiplier': 3, 'unit': 'ppm'}
}

# Default grid size
DEFAULT_GRID_SIZE = 5

# Default advanced simulation settings with detailed descriptions
DEFAULT_ADVANCED_SETTINGS = {
    'ignition_end_time': {
        'value': 0.1, 'unit': 's', 
        'description': (
            'Maximum simulation time for ignition delay calculation. '
            'If ignition does not occur within this time, the delay will be reported as 0.0 or the end time. '
            'Increase this value for very slow ignitions (e.g., at low temperatures or pressures, or for less reactive fuels). '
            'Too high a value will increase calculation time significantly.'
        )
    },
    'ignition_temp_threshold': {
        'value': 100, 'unit': 'K', 
        'description': (
            'Minimum temperature rise from the initial temperature to consider ignition. '
            'A larger value makes ignition detection more robust against small numerical fluctuations. '
            'A smaller value might detect very weak ignitions but can also be triggered by noise. '
            'Default is 100K, suitable for most rapid ignitions.'
        )
    },
    'ignition_detection_method': {
        'value': 'max_dTdt', 'options': ['max_dTdt', 'max_species'], 
        'description': (
            'Method to detect ignition delay: '
            '1. "Maximum Temperature Gradient (max_dTdt)": Detects ignition when the rate of temperature increase is highest. This is a robust general method. '
            '2. "Maximum Concentration of Selected Intermediate Species (max_species)": Detects ignition when the concentration of a specific intermediate radical (like OH, H, O) reaches its peak. This method can be more sensitive for certain fuels or conditions. '
            'Choose max_dTdt if unsure or for general cases. Choose max_species if you know a specific radical is a good indicator for your fuel.'
        )
    },
    'ignition_detection_species': {
        'value': 'OH', 'options': ['OH', 'H', 'O', 'CO', 'CH2O'], 
        'description': (
            'Intermediate species to monitor for ignition delay when using the "max_species" method. '
            '**Recommendations:**\n'
            '- **OH, H, O:** Common highly reactive radicals indicating the start of combustion. '
            '  Generally good for most hydrocarbon fuels and hydrogen.\n'
            '  *OH* is often preferred for general hydrocarbon combustion due to its key role.\n'
            '  *H* or *O* might be better for very simple fuels like hydrogen (H2/O2 system).\n'
            '- **CO (Carbon Monoxide):** Formed during incomplete combustion of carbon-containing fuels. '
            '  Useful if CO formation is a critical indicator for your specific fuel (e.g., fuels with early CO production).\n'
            '- **CH2O (Formaldehyde):** An important intermediate in low-temperature combustion of alkanes. '
            '  Consider for larger alkanes (like Propane) especially at lower initial temperatures where cool flames might occur before hot ignition.'
        )
    },
    'flame_width': {
        'value': 0.05, 'unit': 'm', 
        'description': (
            'Initial domain width for laminar flame speed calculation. '
            'This sets the spatial extent over which the flame structure is calculated. '
            'A larger width may be needed for very thick flames or at very low pressures, but increases computation time. '
            'A smaller width might lead to non-convergence if the flame structure exceeds the domain. '
            'Default 0.05m (5 cm) is usually sufficient for typical atmospheric flames. '
            'If the solver fails to converge, try increasing this value.'
        )
    }
}

class ThresholdSettingsDialog(tk.Toplevel):
    """Dialog window for setting threshold and multiplier values"""
    def __init__(self, parent, thresholds):
        super().__init__(parent)
        self.title("Set Threshold and Multiplier Values")
        self.geometry("500x500")
        self.resizable(False, False)

        self.thresholds = thresholds
        self.result = thresholds.copy()
        self.entries = {}

        # Create main frame
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Create headers
        ttk.Label(main_frame, text="Parameter", font=("Arial", 10, "bold")).grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        ttk.Label(main_frame, text="Threshold Value", font=("Arial", 10, "bold")).grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(main_frame, text="Multiplier", font=("Arial", 10, "bold")).grid(row=0, column=2, padx=5, pady=5)

        row = 1
        for param, values in self.thresholds.items():
            # Get the unit, default to an empty string if not found
            unit = values.get('unit', '')
            display_text = f"{param} [{unit}]" if unit else param
            ttk.Label(main_frame, text=display_text).grid(row=row, column=0, padx=5, pady=5, sticky=tk.W)

            # Threshold entry
            threshold_var = tk.DoubleVar(value=values['threshold'])
            threshold_entry = ttk.Entry(main_frame, textvariable=threshold_var, width=10)
            threshold_entry.grid(row=row, column=1, padx=5, pady=5)

            # Multiplier entry
            multiplier_var = tk.DoubleVar(value=values['multiplier'])
            multiplier_entry = ttk.Entry(main_frame, textvariable=multiplier_var, width=10)
            multiplier_entry.grid(row=row, column=2, padx=5, pady=5)

            self.entries[param] = (threshold_var, multiplier_var)
            row += 1

        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row+1, column=0, columnspan=3, pady=(15, 0))

        ttk.Button(button_frame, text="Save", command=self.save).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Reset Defaults", command=self.reset_defaults).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=5)

    def save(self):
        """Save threshold and multiplier values"""
        for param, (threshold_var, multiplier_var) in self.entries.items():
            try:
                threshold_val = threshold_var.get()
                multiplier_val = multiplier_var.get()

                if multiplier_val <= 0:
                    messagebox.showerror("Invalid Input", f"Multiplier for {param} must be positive")
                    return

                self.result[param] = {
                    'threshold': threshold_val,
                    'multiplier': multiplier_val,
                    'unit': DEFAULT_THRESHOLDS[param].get('unit', '') # Preserve the unit
                }
            except tk.TclError:
                messagebox.showerror("Invalid Input", f"Invalid value for {param}. Using previous value.")
        self.destroy()

    def reset_defaults(self):
        """Reset to default threshold and multiplier values"""
        for param, (threshold_var, multiplier_var) in self.entries.items():
            if param in DEFAULT_THRESHOLDS:
                threshold_var.set(DEFAULT_THRESHOLDS[param]['threshold'])
                multiplier_var.set(DEFAULT_THRESHOLDS[param]['multiplier'])


class AdvancedSettingsDialog(tk.Toplevel):
    """Dialog window for setting advanced simulation parameters"""
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.title("Advanced Simulation Settings")
        self.geometry("600x500")
        self.resizable(False, False)

        self.settings = settings
        self.result = {k: v.copy() for k, v in settings.items()} # Deep copy
        self.entries = {}
        self.vars = {} # To hold Tkinter variables

        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Ignition Delay Settings
        ignition_frame = ttk.LabelFrame(main_frame, text="Ignition Delay Settings", padding="10")
        ignition_frame.pack(fill=tk.X, pady=(0, 10))

        # End Time
        ttk.Label(ignition_frame, text="Simulation End Time:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.vars['ignition_end_time'] = tk.DoubleVar(value=self.settings['ignition_end_time']['value'])
        entry_end_time = ttk.Entry(ignition_frame, textvariable=self.vars['ignition_end_time'], width=10)
        entry_end_time.grid(row=0, column=1, padx=5, pady=2)
        ttk.Label(ignition_frame, text=self.settings['ignition_end_time']['unit']).grid(row=0, column=2, sticky=tk.W, padx=2, pady=2)
        ttk.Button(ignition_frame, text="More Info", command=lambda: self.show_info('ignition_end_time')).grid(row=0, column=3, padx=5, pady=2)
        
        # Temperature Threshold
        ttk.Label(ignition_frame, text="Temperature Threshold:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.vars['ignition_temp_threshold'] = tk.DoubleVar(value=self.settings['ignition_temp_threshold']['value'])
        entry_temp_threshold = ttk.Entry(ignition_frame, textvariable=self.vars['ignition_temp_threshold'], width=10)
        entry_temp_threshold.grid(row=1, column=1, padx=5, pady=2)
        ttk.Label(ignition_frame, text=self.settings['ignition_temp_threshold']['unit']).grid(row=1, column=2, sticky=tk.W, padx=2, pady=2)
        ttk.Button(ignition_frame, text="More Info", command=lambda: self.show_info('ignition_temp_threshold')).grid(row=1, column=3, padx=5, pady=2)

        # Detection Method
        ttk.Label(ignition_frame, text="Detection Method:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.vars['ignition_detection_method'] = tk.StringVar(value=self.settings['ignition_detection_method']['value'])
        method_combo = ttk.Combobox(ignition_frame, textvariable=self.vars['ignition_detection_method'], 
                                    values=self.settings['ignition_detection_method']['options'], state="readonly", width=15)
        method_combo.grid(row=2, column=1, padx=5, pady=2)
        ttk.Button(ignition_frame, text="More Info", command=lambda: self.show_info('ignition_detection_method')).grid(row=2, column=3, padx=5, pady=2)

        # Detection Species (visible only if method is 'max_species')
        ttk.Label(ignition_frame, text="Detection Species:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        self.vars['ignition_detection_species'] = tk.StringVar(value=self.settings['ignition_detection_species']['value'])
        self.species_combo = ttk.Combobox(ignition_frame, textvariable=self.vars['ignition_detection_species'], 
                                           values=self.settings['ignition_detection_species']['options'], state="readonly", width=15)
        self.species_combo.grid(row=3, column=1, padx=5, pady=2)
        ttk.Button(ignition_frame, text="More Info", command=lambda: self.show_info('ignition_detection_species')).grid(row=3, column=3, padx=5, pady=2)
        
        # Link visibility of species combo to method selection
        self.vars['ignition_detection_method'].trace_add('write', self._toggle_species_visibility)
        self._toggle_species_visibility() # Set initial visibility


        # Laminar Flame Speed Settings
        flame_frame = ttk.LabelFrame(main_frame, text="Laminar Flame Speed Settings", padding="10")
        flame_frame.pack(fill=tk.X, pady=(10, 0))

        # Flame Width
        ttk.Label(flame_frame, text="Flame Width:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.vars['flame_width'] = tk.DoubleVar(value=self.settings['flame_width']['value'])
        entry_flame_width = ttk.Entry(flame_frame, textvariable=self.vars['flame_width'], width=10)
        entry_flame_width.grid(row=0, column=1, padx=5, pady=2)
        ttk.Label(flame_frame, text=self.settings['flame_width']['unit']).grid(row=0, column=2, sticky=tk.W, padx=2, pady=2)
        ttk.Button(flame_frame, text="More Info", command=lambda: self.show_info('flame_width')).grid(row=0, column=3, padx=5, pady=2)

        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(15, 0))
        
        ttk.Button(button_frame, text="Save", command=self.save).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Reset Defaults", command=self.reset_defaults).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=5)

    def _toggle_species_visibility(self, *args):
        """Toggles the visibility of the species selection combobox based on the detection method."""
        if self.vars['ignition_detection_method'].get() == 'max_species':
            self.species_combo.grid() # Make visible
            self.species_combo.grid_configure(row=3, column=1) # Re-position
            self.species_combo.master.grid_rowconfigure(3, weight=1) # Ensure row expands
        else:
            self.species_combo.grid_remove() # Hide

    def show_info(self, param_name):
        """Show information about a parameter in a messagebox."""
        info = self.settings[param_name]['description']
        messagebox.showinfo(f"Info: {param_name}", info)

    def save(self):
        """Save advanced settings values, performing validation."""
        for param, var in self.vars.items():
            try:
                if isinstance(var, tk.DoubleVar):
                    val = var.get()
                    if param == 'ignition_end_time' and val <= 0:
                        messagebox.showerror("Invalid Input", "Simulation End Time must be positive.")
                        return
                    if param == 'ignition_temp_threshold' and val <= 0:
                        messagebox.showerror("Invalid Input", "Temperature Threshold must be positive.")
                        return
                    if param == 'flame_width' and val <= 0:
                        messagebox.showerror("Invalid Input", "Flame Width must be positive.")
                        return
                    self.result[param]['value'] = val
                elif isinstance(var, tk.StringVar):
                    self.result[param]['value'] = var.get()
            except tk.TclError:
                messagebox.showerror("Invalid Input", f"Invalid value for {param}.")
                return
        self.destroy()

    def reset_defaults(self):
        """Reset all advanced simulation settings to their default values."""
        for param, var in self.vars.items():
            if param in DEFAULT_ADVANCED_SETTINGS:
                var.set(DEFAULT_ADVANCED_SETTINGS[param]['value'])
        self._toggle_species_visibility() # Update visibility after reset

class CombustionAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Combustion Parameters Analyzer")
        self.root.geometry("600x550") # Increased height to accommodate new widgets
        self.root.resizable(True, True)
        
        # Variables for storing parameters
        self.T_var = tk.DoubleVar(value=1000)
        self.P_var = tk.DoubleVar(value=10)
        self.phi_var = tk.DoubleVar(value=1.0)
        self.fuel_var = tk.StringVar(value="Hydrogen (H2)")
        self.status_var = tk.StringVar(value="Ready for calculations")
        self.progress_var = tk.IntVar(value=0)
        self.grid_size_var = tk.IntVar(value=DEFAULT_GRID_SIZE) # New variable for grid size
        
        # Initialize thresholds with default values
        self.thresholds = {k: v.copy() for k, v in DEFAULT_THRESHOLDS.items()}
        # Initialize advanced settings with default values (deep copy)
        self.advanced_settings = {k: v.copy() for k, v in DEFAULT_ADVANCED_SETTINGS.items()}
        
        # Storing results
        self.input_params = {}
        self.plot_files = []
        self.results_dir = ""
        self.total_time = 0.0
        self.compensation_records = []
        self.logger = None
        self.param1_range = None
        self.param2_range = None
        
        # Dodaj zmienną dla utleniacza
        self.oxidizer_var = tk.StringVar(value="Air")
        
        self.create_widgets()
    
    def create_results_directory(self, base_name="Calc_Results"):
        """Create a unique results directory in script directory"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        counter = 0
        dir_name = os.path.join(script_dir, base_name)
        
        while os.path.exists(dir_name):
            counter += 1
            dir_name = os.path.join(script_dir, f"{base_name}_{counter}")
        
        os.makedirs(dir_name)
        return dir_name
    
    def create_widgets(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Parameters section
        params_frame = ttk.LabelFrame(main_frame, text="Input Parameters", padding="10")
        params_frame.pack(fill=tk.X, pady=(0, 15))

        # Dodaj selektor utleniacza
        ttk.Label(params_frame, text="Oxidizer:").grid(row=0, column=3, sticky=tk.W, padx=5, pady=5)
        oxidizer_combo = ttk.Combobox(params_frame, textvariable=self.oxidizer_var, width=25)
        oxidizer_combo['values'] = tuple(OXIDIZERS.keys())
        oxidizer_combo.grid(row=0, column=4, padx=5, pady=5, sticky=tk.W)
        
        # Fuel selection
        ttk.Label(params_frame, text="Fuel:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        fuel_combo = ttk.Combobox(params_frame, textvariable=self.fuel_var, width=40)
        fuel_combo['values'] = tuple(FUELS.keys())
        fuel_combo.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        
        # Temperature field
        ttk.Label(params_frame, text="Initial temperature [K]:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Label(params_frame, text="Range: 300 - 1500 K").grid(row=1, column=2, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(params_frame, textvariable=self.T_var, width=10).grid(row=1, column=1, padx=5, pady=5)
        
        # Pressure field
        ttk.Label(params_frame, text="Pressure [atm]:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Label(params_frame, text="Range: 0.5 - 50 atm").grid(row=2, column=2, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(params_frame, textvariable=self.P_var, width=10).grid(row=2, column=1, padx=5, pady=5)
        
        # Equivalence ratio field
        ttk.Label(params_frame, text="Equivalence ratio (phi):").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Label(params_frame, text="Range: 0.3 - 4.0").grid(row=3, column=2, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(params_frame, textvariable=self.phi_var, width=10).grid(row=3, column=1, padx=5, pady=5)

        # Grid size selection
        ttk.Label(params_frame, text="Grid Size (NxN):").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        grid_size_combo = ttk.Combobox(params_frame, textvariable=self.grid_size_var, width=10, state="readonly")
        grid_size_combo['values'] = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
        grid_size_combo.grid(row=4, column=1, padx=5, pady=5, sticky=tk.W)
        ttk.Button(params_frame, text="Reset Grid", command=self.reset_grid_size).grid(row=4, column=2, padx=5, pady=5, sticky=tk.W)
        
        # Control buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 15))
        
        self.run_button = ttk.Button(button_frame, text="Run Calculation", command=self.run_calculation)
        self.run_button.pack(side=tk.LEFT, padx=(0, 10))
        
        # Add Threshold Settings button
        ttk.Button(button_frame, text="Threshold Settings", command=self.open_threshold_settings).pack(side=tk.LEFT, padx=(0, 10))
        
        # Add Advanced Simulation Settings button
        ttk.Button(button_frame, text="Advanced Settings", command=self.open_advanced_settings).pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(button_frame, text="Exit", command=self.root.destroy).pack(side=tk.LEFT)
        
        # Progress bar
        ttk.Label(main_frame, text="Calculation progress:").pack(anchor=tk.W)
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, side=tk.LEFT, expand=True)
        ttk.Label(progress_frame, textvariable=self.progress_var, width=4).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Label(progress_frame, text="%").pack(side=tk.RIGHT)
        
        # Status
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X)
        
        ttk.Label(status_frame, text="Status:").pack(side=tk.LEFT)
        ttk.Label(status_frame, textvariable=self.status_var, foreground="blue").pack(side=tk.LEFT, padx=(5, 0))
    
    def open_threshold_settings(self):
        """Open threshold settings dialog"""
        dialog = ThresholdSettingsDialog(self.root, self.thresholds)
        self.root.wait_window(dialog)
        
        # Update thresholds if user saved changes
        if hasattr(dialog, 'result'):
            self.thresholds = dialog.result
            self.status_var.set("Threshold values updated")

    def open_advanced_settings(self):
        """Open advanced simulation settings dialog"""
        dialog = AdvancedSettingsDialog(self.root, self.advanced_settings)
        self.root.wait_window(dialog)

        # Update advanced settings if user saved changes
        if hasattr(dialog, 'result'):
            self.advanced_settings = dialog.result
            self.status_var.set("Advanced simulation settings updated")

    def reset_grid_size(self):
        """Reset grid size to default 5x5"""
        self.grid_size_var.set(DEFAULT_GRID_SIZE)
        self.status_var.set("Grid size reset to 5x5")
    
    def validate_inputs(self):
        """Validate input data"""
        try:
            T = self.T_var.get()
            P = self.P_var.get()
            phi = self.phi_var.get()
            
            if not (300 <= T <= 1500):
                messagebox.showerror("Error", "Temperature must be in range 300-1500 K")
                return False
                
            if not (0.5 <= P <= 50):
                messagebox.showerror("Error", "Pressure must be in range 0.5-50 atm")
                return False
                
            if not (0.3 <= phi <= 4.0):
                messagebox.showerror("Error", "Equivalence ratio must be in range 0.3-4.0")
                return False
                
            return True
            
        except tk.TclError:
            messagebox.showerror("Error", "Invalid numeric values")
            return False
    
    def run_calculation(self):
        """Main function to start calculations"""
        if not self.validate_inputs():
            return
            
        # Get values from GUI
        # Pobierz wartości z GUI
        T = self.T_var.get()
        P = self.P_var.get()
        phi = self.phi_var.get()
        fuel_name = self.fuel_var.get()
        oxidizer_name = self.oxidizer_var.get()  # Nowa zmienna
        grid_size = self.grid_size_var.get()

        self.input_params = {
            'T': T, 
            'P': P, 
            'phi': phi, 
            'fuel': fuel_name,
            'oxidizer': oxidizer_name,  # Dodaj utleniacz
            'grid_size': grid_size
        }
        self.plot_files = []  # Reset file list
        self.compensation_records = []  # Reset compensation records
        
        # Create unique results directory
        self.results_dir = self.create_results_directory()
        self.status_var.set(f"Created results folder: {self.results_dir}")
        self.root.update()
        
        # Setup logging
        self.setup_logger()
        self.logger.info(f"Starting calculation for fuel: {fuel_name}, T={T}K, P={P}atm, phi={phi}, Grid Size: {grid_size}x{grid_size}")
        self.logger.info(f"Advanced Settings: {self.advanced_settings}")
        
        # Update status and disable button
        self.status_var.set("Calculation in progress...")
        self.run_button.config(state=tk.DISABLED)
        self.progress_var.set(0)
        self.root.update()
        
        try:
            # Start timing
            start_time_total = time.time()
            
            # Parameter ranges (using selected grid size)
            T_range = np.linspace(max(300, T-100), min(1500, T+100), grid_size)  # Temperature [K]
            P_range = np.linspace(max(0.5, P-5), min(50, P+5), grid_size)        # Pressure [atm]
            
            # Store ranges for later use
            self.param1_range = T_range
            self.param2_range = P_range
            
            # Generate data for all parameters
            self.status_var.set("Generating 3D surfaces...")
            results = self.generate_3d_surfaces(
                T_range, 
                P_range, 
                {'T': T, 'P': P, 'phi': phi}
            )
            
            # Unpack results based on fuel type
            if FUELS[fuel_name]['has_carbon']:
                X, Y, Z_tad, Z_ignition, Z_flame, Z_nox, Z_co, Z_co2 = results
            else:
                X, Y, Z_tad, Z_ignition, Z_flame, Z_nox = results
                Z_co = None  # Ensure Z_co is defined as None if not carbon-based
                Z_co2 = None # Ensure Z_co2 is defined as None if not carbon-based
            
            # Generate plots
            self.status_var.set("Creating plots...")
            self.create_plots(X, Y, Z_tad, Z_ignition, Z_flame, Z_nox, FUELS[fuel_name]['has_carbon'], Z_co, Z_co2)
            
            # Generate PDF report
            self.status_var.set("Creating PDF report...")
            self.root.update()
            
            # Calculate total time
            self.total_time = time.time() - start_time_total
            pdf_file = self.generate_pdf_report()
            
            self.status_var.set(f"Calculation completed in {self.total_time:.2f} seconds!")
            self.logger.info(f"Calculation completed successfully in {self.total_time:.2f} seconds")
            messagebox.showinfo("Success", f"Calculation completed in {self.total_time:.2f} seconds!\nResults saved in: {self.results_dir}\nReport: {pdf_file}")
            
        except Exception as e:
            # Replace any special characters in error message
            error_msg = str(e).replace('\u03c6', 'phi')  # Replace φ with phi
            self.status_var.set(f"Error: {error_msg}")
            self.logger.error(f"Calculation error: {error_msg}", exc_info=True)
            messagebox.showerror("Calculation Error", f"An error occurred during calculations:\n{error_msg}")
        
        finally:
            self.run_button.config(state=tk.NORMAL)
            if self.logger:
                # Close all handlers to release the log file
                for handler in self.logger.handlers[:]:
                    handler.close()
                    self.logger.removeHandler(handler)
    
    def setup_logger(self):
        """Set up logging to a file in results directory with UTF-8 encoding"""
        log_file = os.path.join(self.results_dir, "log.txt")
        self.logger = logging.getLogger("CombustionAnalyzer")
        self.logger.setLevel(logging.INFO)
        
        # Ensure handlers are not duplicated
        if not self.logger.handlers:
            # Create file handler with UTF-8 encoding
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.INFO)
            
            # Create formatter
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
            
            # Add handlers to logger
            self.logger.addHandler(file_handler)
        self.logger.info("Logging initialized")
    
    def safe_filename(self, name):
        """Create a safe filename by removing invalid characters"""
        return re.sub(r'[\\/*?:"<>|\[\] ]', "_", name)
    
    def calculate_combustion_params(self, T, P, phi):
        """Calculate all combustion parameters for given initial conditions"""
        results = {}
        fuel_name = self.fuel_var.get()
        fuel_info = FUELS[fuel_name]
        oxidizer = OXIDIZERS[self.oxidizer_var.get()]  # Pobierz skład utleniacza
        
        try:
            # Initialize mixture
            gas = ct.Solution(fuel_info["mechanism"])
            gas.TP = T, P * ct.one_atm  # Convert to Pa
            
            # Ustaw skład mieszanki
            try:
                gas.set_equivalence_ratio(phi, fuel_info["formula"], oxidizer)
            except ct.CanteraError as e:
                self.logger.error(f"Composition error: {str(e)}")
                # Próba ręcznego ustawienia składu
                gas.set_equivalence_ratio(phi, fuel_info["formula"], oxidizer)
            
            # 1. Adiabatic temperature
            gas_ad = ct.Solution(fuel_info["mechanism"])
            gas_ad.TPX = gas.TPX  # Copy state
            gas_ad.equilibrate('HP')
            results['T_ad'] = gas_ad.T
            
            # 2. Ignition delay time
            reactor = ct.IdealGasReactor(gas)
            net = ct.ReactorNet([reactor])
            
            times = []
            temperatures = []
            species_conc = [] # To store species concentration for max_species method
            
            current_time = 0.0
            end_time = self.advanced_settings['ignition_end_time']['value'] # From advanced settings
            
            # Get selected species for detection
            detection_species = self.advanced_settings['ignition_detection_species']['value']
            
            # Time integration
            while current_time < end_time:
                try:
                    current_time = net.step()
                except Exception as e:
                    self.logger.warning(f"ReactorNet step failed at time {current_time:.2e}s for T={T}K, P={P}atm, phi={phi}: {e}")
                    break # Break the loop if step fails
                
                times.append(current_time)
                temperatures.append(reactor.T)
                
                if self.advanced_settings['ignition_detection_method']['value'] == 'max_species':
                    try:
                        # Check if the species exists in the current mechanism
                        if detection_species in reactor.thermo.species_names:
                            species_conc.append(reactor.thermo[detection_species].X[0])
                        else:
                            # Fallback if species is not found in this mechanism
                            self.logger.warning(f"Selected species '{detection_species}' not found in mechanism '{fuel_info['mechanism']}'. Switching to max_dTdt for ignition delay.")
                            self.advanced_settings['ignition_detection_method']['value'] = 'max_dTdt' 
                            species_conc = [] # Clear incomplete data
                            break # Exit this loop and re-evaluate detection method
                    except Exception as e:
                        self.logger.warning(f"Error getting species concentration for '{detection_species}' at T={T}K, P={P}atm, phi={phi}: {e}")
                        self.advanced_settings['ignition_detection_method']['value'] = 'max_dTdt' 
                        species_conc = []
                        break

            ignition_delay = 0.0
            temp_threshold = self.advanced_settings['ignition_temp_threshold']['value']

            # Ensure there is enough data for gradient calculation and significant temperature rise
            if len(times) > 3 and (max(temperatures) - T) > temp_threshold:
                if self.advanced_settings['ignition_detection_method']['value'] == 'max_dTdt':
                    dTdt = np.gradient(temperatures, times)
                    ignition_delay = times[np.argmax(dTdt)]
                elif self.advanced_settings['ignition_detection_method']['value'] == 'max_species' and species_conc and len(species_conc) == len(times):
                    # Ensure species_conc array is complete and valid
                    dYdt_species = np.gradient(species_conc, times)
                    ignition_delay = times[np.argmax(dYdt_species)]
                else:
                    self.logger.warning(f"Ignition detection method '{self.advanced_settings['ignition_detection_method']['value']}' could not be applied or data insufficient. Defaulting to max_dTdt.")
                    # Fallback if max_species fails or data is bad
                    if len(times) > 3:
                        dTdt = np.gradient(temperatures, times)
                        ignition_delay = times[np.argmax(dTdt)]
                    else:
                        self.logger.warning(f"Insufficient data for ignition delay calculation for T={T}K, P={P}atm, phi={phi}. Setting to 0.0.")
                        ignition_delay = 0.0 # Default to 0 if not enough data
            else:
                self.logger.info(f"No significant temperature rise or insufficient data for ignition for T={T}K, P={P}atm, phi={phi}. Setting ignition delay to 0.0.")
                ignition_delay = 0.0 # No ignition detected
            
            results['ignition_delay'] = ignition_delay * 1e6  # μs
            
            # 3. Laminar flame propagation speed
            try:
                # Use gas copy for flame calculations
                gas_flame = ct.Solution(fuel_info["mechanism"])
                gas_flame.TPX = gas.TPX
                
                # Improved flame solver settings
                flame_width = self.advanced_settings['flame_width']['value'] # From advanced settings
                flame = ct.FreeFlame(gas_flame, width=flame_width)
                flame.set_refine_criteria(ratio=3, slope=0.1, curve=0.1)
                flame.set_max_jac_age(50, 50)  # Improved solver stability
                flame.set_time_step(1e-6, [0.1, 2.0])  # Better time stepping
                
                # Try to solve the flame
                try:
                    flame.solve(loglevel=0, auto=True, stage=2)
                except Exception as e:
                    self.logger.warning(f"Flame solver failed for T={T}K, P={P}atm, phi={phi}: {e}. Attempting with different initial guess or width.")
                    # Attempt a retry with different conditions if needed, or simply assign 0
                    results['flame_speed'] = 0.0
                    
                if 'flame_speed' not in results: # If solver didn't fail
                    # Check if flame.velocity has at least one element before accessing
                    if flame.velocity.size > 0 and flame.velocity[0] > 0: # Ensure positive speed
                        results['flame_speed'] = flame.velocity[0]  # m/s
                    else:
                        results['flame_speed'] = 0.0
                        self.logger.warning(f"Flame speed calculation yielded non-positive velocity for T={T}K, P={P}atm, phi={phi}. Setting to 0.0.")
            except Exception as e:
                self.logger.error(f"Flame speed error for T={T}K, P={P}atm, phi={phi}: {str(e)}", exc_info=True)
                results['flame_speed'] = 0.0
            
            # 4. NOx emission (additional)
            # Check for species existence robustly
            results['NO'] = gas_ad['NO'].X[0] * 1e6 if 'NO' in gas_ad.species_names else 0
            results['NO2'] = gas_ad['NO2'].X[0] * 1e6 if 'NO2' in gas_ad.species_names else 0
            results['NOx'] = results['NO'] + results['NO2']
            
            # 5. CO and CO2 emissions for carbon-based fuels
            results['CO'] = gas_ad['CO'].X[0] * 1e6 if fuel_info['has_carbon'] and 'CO' in gas_ad.species_names else 0
            results['CO2'] = gas_ad['CO2'].X[0] * 1e6 if fuel_info['has_carbon'] and 'CO2' in gas_ad.species_names else 0
            
        except Exception as e:
            self.logger.error(f"General calculation error for T={T}K, P={P}atm, phi={phi}: {str(e)}", exc_info=True)
            results = {
                'T_ad': 0,
                'ignition_delay': 0,
                'flame_speed': 0,
                'NO': 0,
                'NO2': 0,
                'NOx': 0,
                'CO': 0,
                'CO2': 0
            }
        
        # Log any zero values that might indicate issues
        for param, value in results.items():
            if value == 0 and param != 'CO2': # CO2 can legitimately be 0 in non-carbon fuels
                self.logger.debug(f"Parameter '{param}' is 0 for T={T}K, P={P}atm, phi={phi}. This might indicate a non-physical result or calculation failure.")

        return results
    
    def compensate_outliers(self, arr, param_name):
        """Compensate extreme values in array with neighbors median multiplied by user-defined factor"""
        compensated_arr = arr.copy()
        rows, cols = arr.shape
        records = []
        
        # Get threshold and multiplier for this parameter
        param_settings = self.thresholds.get(param_name, {})
        threshold_val = param_settings.get('threshold', float('inf'))
        multiplier = param_settings.get('multiplier', 3.0)
        
        for i in range(rows): # i is row index (for P_range)
            for j in range(cols): # j is column index (for T_range)
                value = arr[i, j]
                
                # Check for outliers: NaN, Inf, negative flame speed, or value above threshold
                is_outlier = (np.isnan(value) or np.isinf(value) or 
                              (param_name == 'flame_speed' and value < 0) or 
                              abs(value) > threshold_val)
                
                # Special handling for ignition_delay and flame_speed if they are exactly 0
                # These might be true 'no ignition' or 'no propagation', but also can be solver failures.
                # If they are 0 and there are valid non-zero neighbors, we assume it's an outlier.
                if (param_name in ['ignition_delay', 'flame_speed']) and np.isclose(value, 0.0, atol=1e-9):
                    # Check if there are any non-zero neighbors. If so, treat 0 as outlier for compensation.
                    has_non_zero_neighbor = False
                    for di in [-1, 0, 1]:
                        for dj in [-1, 0, 1]:
                            if di == 0 and dj == 0: continue
                            ni, nj = i + di, j + dj
                            if 0 <= ni < rows and 0 <= nj < cols:
                                neighbor_val = arr[ni, nj]
                                if not (np.isnan(neighbor_val) or np.isinf(neighbor_val) or np.isclose(neighbor_val, 0.0, atol=1e-9)):
                                    has_non_zero_neighbor = True
                                    break
                        if has_non_zero_neighbor: break
                    
                    if has_non_zero_neighbor:
                        is_outlier = True # Treat 0 as an outlier if surrounded by valid non-zero data
                        self.logger.info(f"Identified 0 value as potential outlier for '{param_name}' at T={self.param1_range[j]}K, P={self.param2_range[i]}atm due to non-zero neighbors.")
                
                if not is_outlier:
                    continue # Skip if not an outlier
                
                # Gather neighbors (excluding self, and excluding other outliers/invalid values)
                neighbors = []
                for di in [-1, 0, 1]:
                    for dj in [-1, 0, 1]:
                        if di == 0 and dj == 0:
                            continue
                        ni, nj = i + di, j + dj
                        if 0 <= ni < rows and 0 <= nj < cols:
                            neighbor_val = arr[ni, nj]
                            # Only consider valid, non-outlier neighbors for median calculation
                            if not (np.isnan(neighbor_val) or np.isinf(neighbor_val) or 
                                    (param_name == 'flame_speed' and neighbor_val < 0) or 
                                    abs(neighbor_val) > threshold_val or 
                                    (param_name in ['ignition_delay', 'flame_speed'] and np.isclose(neighbor_val, 0.0, atol=1e-9))): # Don't use 0 as a valid neighbor for ign_delay/flame_speed
                                neighbors.append(neighbor_val)
                
                # Calculate median of neighbors if possible
                if neighbors:
                    median_val = np.median(neighbors)
                    new_value = median_val * multiplier
                    
                    # Ensure new value doesn't exceed threshold (unless the threshold is infinity)
                    if threshold_val != float('inf') and new_value > threshold_val:
                        new_value = threshold_val
                    
                    # Ensure flame speed and ignition delay remain non-negative
                    if param_name in ['ignition_delay', 'flame_speed'] and new_value < 0:
                        new_value = 0.0
                    
                    # Apply compensation
                    compensated_arr[i, j] = new_value
                    
                    # Record compensation
                    # T_val corresponds to column (j), P_val corresponds to row (i)
                    T_val = self.param1_range[j]
                    P_val = self.param2_range[i]
                    records.append({
                        'param': param_name,
                        'T': T_val,
                        'P': P_val,
                        'original': value,
                        'compensated': new_value,
                        'reason': f"Extreme value ({value:.2e})"
                    })
                    self.logger.info(
                        f"Compensated {param_name} at T={T_val}K, P={P_val}atm: "
                        f"{value:.2e} -> {new_value:.2e} (multiplier: {multiplier}, threshold: {threshold_val})"
                    )
                else:
                    # If no valid neighbors, set to a default 'bad' value (e.g., NaN or a fixed small value like 1e-9 for physics-related zeros)
                    # For ignition delay and flame speed, if no valid neighbors, assume non-ignition/no propagation.
                    if param_name in ['ignition_delay', 'flame_speed']:
                        compensated_arr[i, j] = 0.0 # Keep as 0 if no valid neighbors to derive a value
                        self.logger.warning(
                            f"Could not compensate {param_name} at index [{i},{j}] (T={self.param1_range[j]}K, P={self.param2_range[i]}atm) "
                            f"due to no valid neighbors. Original value was {value:.2e}. Keeping as 0.0."
                        )
                    else:
                        compensated_arr[i, j] = np.nan # Or some other indicator of failure
                        self.logger.warning(
                            f"Could not compensate {param_name} at index [{i},{j}] (T={self.param1_range[j]}K, P={self.param2_range[i]}atm) "
                            f"due to no valid neighbors. Original value: {value:.2e}. Setting to NaN."
                        )

        return compensated_arr, records
    
    def generate_3d_surfaces(self, param1_range, param2_range, fixed_params):
        """Generate 3D surfaces for all output parameters"""
        X, Y = np.meshgrid(param1_range, param2_range)
        Z_tad = np.zeros_like(X, dtype=float)
        Z_ignition = np.zeros_like(X, dtype=float)
        Z_flame = np.zeros_like(X, dtype=float)
        Z_nox = np.zeros_like(X, dtype=float)
        
        # Initialize CO and CO2 arrays only for carbon-based fuels
        fuel_name = self.fuel_var.get()
        if FUELS[fuel_name]['has_carbon']:
            Z_co = np.zeros_like(X, dtype=float)
            Z_co2 = np.zeros_like(X, dtype=float)
        else:
            Z_co = None # Explicitly set to None
            Z_co2 = None # Explicitly set to None
        
        total_points = len(param1_range) * len(param2_range)
        self.status_var.set(f"Started calculations for {total_points} points...")
        self.root.update()
        
        start_time = time.time()
        points_done = 0
        
        for i, p2_val in enumerate(param2_range): # Iterate over rows (P_range)
            for j, p1_val in enumerate(param1_range): # Iterate over columns (T_range)
                
                # Calculations
                results = self.calculate_combustion_params(
                    T=p1_val, # T from param1_range (columns)
                    P=p2_val, # P from param2_range (rows)
                    phi=fixed_params['phi'] # phi is fixed
                )
                
                # Save results to the correct [row, column] position
                Z_tad[i, j] = results['T_ad']
                Z_ignition[i, j] = results['ignition_delay']
                Z_flame[i, j] = results['flame_speed']
                Z_nox[i, j] = results['NOx']
                
                # Save CO/CO2 for carbon-based fuels
                if FUELS[fuel_name]['has_carbon']:
                    Z_co[i, j] = results['CO']
                    Z_co2[i, j] = results['CO2']
                
                # Update progress
                points_done += 1
                progress = int(points_done / total_points * 100)
                self.progress_var.set(progress)
                
                elapsed = time.time() - start_time
                time_per_point = elapsed / points_done if points_done > 0 else 0
                remaining = (total_points - points_done) * time_per_point
                
                self.status_var.set(
                    f"Calculation: {points_done}/{total_points} points "
                    f"({progress}%) | Remaining: {remaining:.0f}s"
                )
                self.root.update()
        
        elapsed_time = time.time() - start_time
        self.status_var.set(f"Raw data calculation completed in {elapsed_time:.2f} seconds")
        self.logger.info(f"Raw data calculation completed in {elapsed_time:.2f} seconds")
        
        # Compensate outliers for all parameters
        self.logger.info("Compensating outliers...")
        
        # Compensate each parameter array
        Z_tad, rec_tad = self.compensate_outliers(Z_tad, 'T_ad')
        Z_ignition, rec_ign = self.compensate_outliers(Z_ignition, 'ignition_delay')
        Z_flame, rec_flame = self.compensate_outliers(Z_flame, 'flame_speed')
        Z_nox, rec_nox = self.compensate_outliers(Z_nox, 'NOx')
        
        self.compensation_records.extend(rec_tad)
        self.compensation_records.extend(rec_ign)
        self.compensation_records.extend(rec_flame)
        self.compensation_records.extend(rec_nox)
        
        if FUELS[fuel_name]['has_carbon']:
            Z_co, rec_co = self.compensate_outliers(Z_co, 'CO')
            Z_co2, rec_co2 = self.compensate_outliers(Z_co2, 'CO2')
            self.compensation_records.extend(rec_co)
            self.compensation_records.extend(rec_co2)
            return X, Y, Z_tad, Z_ignition, Z_flame, Z_nox, Z_co, Z_co2
        else:
            # If not carbon-based, Z_co and Z_co2 might be None.
            # We return them as None to create_plots which handles it.
            return X, Y, Z_tad, Z_ignition, Z_flame, Z_nox
    
    def create_plots(self, X, Y, Z_tad, Z_ignition, Z_flame, Z_nox, has_carbon, Z_co=None, Z_co2=None):
        """Create and save all plots"""
        # 1. Plot for adiabatic temperature
        self.plot_3d_surface(X, Y, Z_tad, 'Temperature [K]', 'Pressure [atm]', 'Adiabatic_Temperature_K')
        self.plot_contour(X, Y, Z_tad, 'Temperature [K]', 'Pressure [atm]', 'Adiabatic_Temperature_K')
        
        # 2. Plot for ignition delay
        self.plot_3d_surface(X, Y, Z_ignition, 'Temperature [K]', 'Pressure [atm]', 'Ignition_Delay_us')
        self.plot_contour(X, Y, Z_ignition, 'Temperature [K]', 'Pressure [atm]', 'Ignition_Delay_us')
        
        # 3. Plot for flame speed
        self.plot_3d_surface(X, Y, Z_flame, 'Temperature [K]', 'Pressure [atm]', 'Flame_Speed_m_s')
        self.plot_contour(X, Y, Z_flame, 'Temperature [K]', 'Pressure [atm]', 'Flame_Speed_m_s')
        
        # 4. Plot for NOx emissions
        self.plot_3d_surface(X, Y, Z_nox, 'Temperature [K]', 'Pressure [atm]', 'NOx_Emission_ppm')
        self.plot_contour(X, Y, Z_nox, 'Temperature [K]', 'Pressure [atm]', 'NOx_Emission_ppm')
        
        # 5. Plots for CO and CO2 emissions (only for carbon-based fuels)
        if has_carbon:
            # CO emissions
            self.plot_3d_surface(X, Y, Z_co, 'Temperature [K]', 'Pressure [atm]', 'CO_Emission_ppm')
            self.plot_contour(X, Y, Z_co, 'Temperature [K]', 'Pressure [atm]', 'CO_Emission_ppm', CO_COLORS)
            
            # CO2 emissions
            self.plot_3d_surface(X, Y, Z_co2, 'Temperature [K]', 'Pressure [atm]', 'CO2_Emission_ppm')
            self.plot_contour(X, Y, Z_co2, 'Temperature [K]', 'Pressure [atm]', 'CO2_Emission_ppm', CO2_COLORS)
    
    def plot_3d_surface(self, X, Y, Z, param1_name, param2_name, output_label):
        """Create and save 3D plot"""
        try:
            fig = go.Figure(data=[
                go.Surface(
                    z=Z,
                    x=X,
                    y=Y,
                    colorscale='Viridis',
                    opacity=0.9,
                    contours={
                        "z": {"show": True, "usecolormap": True, "highlightcolor": "limegreen"}
                    }
                )
            ])
            
            fig.update_layout(
                title=f'{output_label} vs {param1_name} and {param2_name}',
                scene=dict(
                    xaxis_title=param1_name,
                    yaxis_title=param2_name,
                    zaxis_title=output_label,
                    camera_eye=dict(x=1.5, y=1.5, z=0.8)
                ),
                height=800,
                margin=dict(l=65, r=50, b=65, t=90)
            )
            
            # Save to HTML file
            safe_label = self.safe_filename(output_label)
            html_filename = os.path.join(self.results_dir, f"3d_plot_{safe_label}.html")
            fig.write_html(html_filename)
            
            # Save to PNG file for PDF report
            png_filename = os.path.join(self.results_dir, f"3d_plot_{safe_label}.png")
            fig.write_image(png_filename, width=1200, height=800)
            self.plot_files.append(('3d', output_label, png_filename))
            
            self.status_var.set(f"Saved 3D plot: {html_filename}")
            self.root.update()
            
        except Exception as e:
            self.status_var.set(f"3D plot error: {str(e)}")
            self.logger.error(f"3D plot error for {output_label}: {str(e)}", exc_info=True)
    
    def plot_contour(self, X, Y, Z, param1_name, param2_name, output_label, cmap=None):
        """Create and save contour plot"""
        try:
            plt.figure(figsize=(10, 8))
            
            # Determine colormap
            if cmap:
                pass  # Use provided colormap
            elif 'NOx' in output_label or 'NO' in output_label or 'NO2' in output_label:
                cmap = NOX_COLORS
            elif 'CO_' in output_label:
                cmap = CO_COLORS
            elif 'CO2_' in output_label:
                cmap = CO2_COLORS
            else:
                cmap = FLAME_COLORS
            
            contour = plt.contourf(X, Y, Z, 20, cmap=cmap)
            plt.colorbar(contour, label=output_label)
            plt.xlabel(param1_name)
            plt.ylabel(param2_name)
            plt.title(f'{output_label} vs {param1_name} and {param2_name}')
            plt.grid(True, alpha=0.3)
            
            # Save to PNG file
            safe_label = self.safe_filename(output_label)
            filename = os.path.join(self.results_dir, f"contour_{safe_label}.png")
            plt.savefig(filename)
            plt.close()  # Close figure to free memory
            self.plot_files.append(('contour', output_label, filename))
            
            self.status_var.set(f"Saved contour plot: {filename}")
            self.root.update()
            
        except Exception as e:
            self.status_var.set(f"Contour plot error: {str(e)}")
            self.logger.error(f"Contour plot error for {output_label}: {str(e)}", exc_info=True)
    
    def generate_pdf_report(self):
        """Generate PDF report with results"""
        # Helper function to replace Unicode characters
        def ascii_safe(text):
            replacements = {
                '\u2080': '0', '\u2081': '1', '\u2082': '2', 
                '\u2083': '3', '\u2084': '4', '\u2085': '5',
                '\u2086': '6', '\u2087': '7', '\u2088': '8', '\u2089': '9',
                '\u03c6': 'phi',  # Greek phi
                '\u0394': 'delta',  # Greek delta
                '\u00b0': 'deg',    # Degree symbol
                '\u2013': '-',      # En dash
                '\u2014': '--',     # Em dash
                '\u2018': "'",      # Left single quote
                '\u2019': "'",      # Right single quote
                '\u201c': '"',      # Left double quote
                '\u201d': '"',      # Right double quote
                '\u00b5': 'u',      # Micro symbol
                '\u03bc': 'u',      # Greek mu (micro)
                '\u221e': 'inf',    # Infinity
                '\u2260': '!=',     # Not equal
                '\u2264': '<=',     # Less or equal
                '\u2265': '>=',     # Greater or equal
                '\u00b1': '+/-',    # Plus-minus
                '\u00d7': 'x',      # Multiplication sign
                '\u00f7': '/',      # Division sign
                '\u00b2': '2',      # Superscript 2
                '\u00b3': '3'       # Superscript 3
            }
            for uni, ascii in replacements.items():
                text = text.replace(uni, ascii)
            return text

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        # Title page
        pdf.add_page()
        pdf.set_font("Helvetica", 'B', 24) 
        
        # Handle FPDF API change
        if FPDF_NEW_API:
            pdf.cell(0, 40, "Combustion Analysis Report ", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.cell(0, 40, "Combustion Analysis Report", align='C', ln=True)
            
        pdf.ln(20)
        
        # Input parameters - use ASCII-safe versions
        pdf.set_font("Helvetica", 'B', 16)
        if FPDF_NEW_API:
            pdf.cell(0, 10, "Input Parameters:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.cell(0, 10, "Input Parameters:", ln=True)
            
        pdf.set_font("Helvetica", '', 14)
        
        # Convert all strings to ASCII-safe
        safe_fuel = ascii_safe(self.input_params['fuel'])
        safe_oxidizer = ascii_safe(self.input_params['oxidizer'])
        if FPDF_NEW_API:
            pdf.cell(0, 10, f"Fuel: {safe_fuel}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 10, f"Initial temperature (T): {self.input_params['T']} K", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 10, f"Pressure (P): {self.input_params['P']} atm", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 10, f"Equivalence ratio (phi): {self.input_params['phi']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 10, f"Grid Size (NxN): {self.input_params['grid_size']}x{self.input_params['grid_size']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 10, f"Oxidizer: {safe_oxidizer}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        else:
            pdf.cell(0, 10, f"Fuel: {safe_fuel}", ln=True)
            pdf.cell(0, 10, f"Initial temperature (T): {self.input_params['T']} K", ln=True)
            pdf.cell(0, 10, f"Pressure (P): {self.input_params['P']} atm", ln=True)
            pdf.cell(0, 10, f"Equivalence ratio (phi): {self.input_params['phi']}", ln=True)
            pdf.cell(0, 10, f"Grid Size (NxN): {self.input_params['grid_size']}x{self.input_params['grid_size']}", ln=True)
            pdf.cell(0, 10, f"Oxidizer: {safe_oxidizer}", ln=True)
 
            pdf.ln(5)  
        
        # Calculation statistics
        pdf.set_font("Helvetica", 'B', 14)
        if FPDF_NEW_API:
            pdf.cell(0, 10, "Calculation Statistics:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.cell(0, 10, "Calculation Statistics:", ln=True)
            
        pdf.set_font("Helvetica", '', 14)
        total_points_calculated = self.input_params['grid_size'] * self.input_params['grid_size']
        if FPDF_NEW_API:
            pdf.cell(0, 10, f"Total points calculated: {total_points_calculated}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 10, f"Total calculation time: {self.total_time:.2f} seconds", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.cell(0, 10, f"Total points calculated: {total_points_calculated}", ln=True)
            pdf.cell(0, 10, f"Total calculation time: {self.total_time:.2f} seconds", ln=True)
            
        pdf.ln(10)
        
        # Thresholds section
        pdf.set_font("Helvetica", 'B', 14)
        if FPDF_NEW_API:
            pdf.cell(0, 10, "Outlier Compensation Settings:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.cell(0, 10, "Outlier Compensation Settings:", ln=True)
            
        pdf.set_font("Helvetica", '', 12)
        if FPDF_NEW_API:
            pdf.cell(0, 10, "Parameters used for outlier compensation:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.cell(0, 10, "Parameters used for outlier compensation:", ln=True)
            
        pdf.ln(5)
        
        # Add thresholds table
        col_widths = [60, 60, 60]  # Three columns
        if FPDF_NEW_API:
            # Header
            pdf.set_font("Helvetica", 'B', 12)
            pdf.cell(col_widths[0], 10, "Parameter", border=1, align='C')
            pdf.cell(col_widths[1], 10, "Threshold", border=1, align='C')
            pdf.cell(col_widths[2], 10, "Multiplier", border=1, align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", '', 12)
            
            # Data rows
            for param, settings in self.thresholds.items():
                pdf.cell(col_widths[0], 10, param, border=1)
                pdf.cell(col_widths[1], 10, str(settings['threshold']), border=1)
                pdf.cell(col_widths[2], 10, str(settings['multiplier']), border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            # Header
            pdf.set_font("Helvetica", 'B', 12)
            pdf.cell(col_widths[0], 10, "Parameter", border=1, align='C')
            pdf.cell(col_widths[1], 10, "Threshold", border=1, align='C')
            pdf.cell(col_widths[2], 10, "Multiplier", border=1, align='C', ln=True)
            pdf.set_font("Helvetica", '', 12)
            
            # Data rows
            for param, settings in self.thresholds.items():
                pdf.cell(col_widths[0], 10, param, border=1)
                pdf.cell(col_widths[1], 10, str(settings['threshold']), border=1)
                pdf.cell(col_widths[2], 10, str(settings['multiplier']), border=1, ln=True)
        
        pdf.ln(10)

        # Advanced Settings Section in PDF
        pdf.set_font("Helvetica", 'B', 14)
        if FPDF_NEW_API:
            pdf.cell(0, 10, "Advanced Simulation Settings:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.cell(0, 10, "Advanced Simulation Settings:", ln=True)
            
        pdf.set_font("Helvetica", '', 12)
        if FPDF_NEW_API:
            pdf.cell(0, 10, "Configured parameters for simulation mechanisms:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.cell(0, 10, "Configured parameters for simulation mechanisms:", ln=True)
            
        pdf.ln(5)

        # Add advanced settings table
        col_widths_adv = [80, 50, 50] # Param, Value, Unit
        if FPDF_NEW_API:
            # Header
            pdf.set_font("Helvetica", 'B', 12)
            pdf.cell(col_widths_adv[0], 10, "Parameter", border=1, align='C')
            pdf.cell(col_widths_adv[1], 10, "Value", border=1, align='C')
            pdf.cell(col_widths_adv[2], 10, "Unit", border=1, align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", '', 12)

            # Data rows
            for param, settings in self.advanced_settings.items():
                unit = settings.get('unit', '')
                value = settings['value']
                # Special handling for options
                if 'options' in settings:
                    value = value # Display string directly
                
                pdf.cell(col_widths_adv[0], 10, ascii_safe(param), border=1)
                pdf.cell(col_widths_adv[1], 10, str(value), border=1)
                pdf.cell(col_widths_adv[2], 10, unit, border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            # Header
            pdf.set_font("Helvetica", 'B', 12)
            pdf.cell(col_widths_adv[0], 10, "Parameter", border=1, align='C')
            pdf.cell(col_widths_adv[1], 10, "Value", border=1, align='C')
            pdf.cell(col_widths_adv[2], 10, "Unit", border=1, align='C', ln=True)
            pdf.set_font("Helvetica", '', 12)

            # Data rows
            for param, settings in self.advanced_settings.items():
                unit = settings.get('unit', '')
                value = settings['value']
                if 'options' in settings:
                    value = value
                
                pdf.cell(col_widths_adv[0], 10, ascii_safe(param), border=1)
                pdf.cell(col_widths_adv[1], 10, str(value), border=1)
                pdf.cell(col_widths_adv[2], 10, unit, border=1, ln=True)

        pdf.ln(10)
        
        # Add date and time
        pdf.set_font("Helvetica", 'I', 12)
        if FPDF_NEW_API:
            pdf.cell(0, 10, f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.cell(0, 10, f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}", ln=True)
            
        pdf.ln(5)
        
        # Results location
        pdf.set_font("Helvetica", 'I', 12)
        if FPDF_NEW_API:
            pdf.cell(0, 10, f"Results directory: {self.results_dir}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.cell(0, 10, f"Results directory: {self.results_dir}", ln=True)
        
        # Add compensated data points section
        if self.compensation_records:
            pdf.add_page()
            pdf.set_font("Helvetica", 'B', 16)
            if FPDF_NEW_API:
                pdf.cell(0, 10, "Compensated Data Points", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            else:
                pdf.cell(0, 10, "Compensated Data Points", ln=True)
            
            pdf.ln(10)
            pdf.set_font("Helvetica", '', 12)
            
            for record in self.compensation_records:
                text = (f"{record['param']} at T={record['T']}K, P={record['P']}atm: "
                        f"Original value {record['original']:.4g} was compensated to "
                        f"{record['compensated']:.4g} ({record['reason']})")
                if FPDF_NEW_API:
                    pdf.multi_cell(0, 8, ascii_safe(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                else:
                    pdf.multi_cell(0, 8, ascii_safe(text))
                pdf.ln(2)
        
        # Add section with realism notes
        pdf.add_page()
        pdf.set_font("Helvetica", 'B', 16)
        if FPDF_NEW_API:
            pdf.cell(0, 10, "Important Notes on Physical Realism", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.cell(0, 10, "Important Notes on Physical Realism", ln=True)
            
        pdf.ln(10)
        
        pdf.set_font("Helvetica", '', 12)
        
        # Ignition Delay Notes
        pdf.set_font("Helvetica", 'B', 12)
        if FPDF_NEW_API:
            pdf.cell(0, 10, "Ignition Delay Plots:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.cell(0, 10, "Ignition Delay Plots:", ln=True)
            
        pdf.set_font("Helvetica", '', 12)
        notes = [
            "- Extremely short or zero delay times may indicate non-ignition within simulation time",
            "- At low temperatures or pressures, ignition may not occur, leading to reported 0.0 values",
            "- True zero ignition delay is non-physical as there's always finite time for reactions",
            "- Flat areas at zero likely indicate conditions outside flammability limits",
            f"- Current detection method: {self.advanced_settings['ignition_detection_method']['value']} (Species: {self.advanced_settings['ignition_detection_species']['value']})"
        ]
        for note in notes:
            if FPDF_NEW_API:
                pdf.cell(10)  # Indent
                pdf.multi_cell(0, 6, ascii_safe(note), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            else:
                pdf.cell(10)  # Indent
                pdf.multi_cell(0, 6, ascii_safe(note))
            pdf.ln(2)
        
        pdf.ln(5)
        
        # NOx Emission Notes
        pdf.set_font("Helvetica", 'B', 12)
        if FPDF_NEW_API:
            pdf.cell(0, 10, "NOx Emission Plots:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.cell(0, 10, "NOx Emission Plots:", ln=True)
            
        pdf.set_font("Helvetica", '', 12)
        notes = [
            "- Equilibrium calculations often overpredict real-world NOx emissions",
            "- NOx formation is kinetically limited and may not reach equilibrium in practical systems",
            "- Factors like flame quenching limit actual NOx below equilibrium predictions"
        ]
        for note in notes:
            if FPDF_NEW_API:
                pdf.cell(10)
                pdf.multi_cell(0, 6, ascii_safe(note), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            else:
                pdf.cell(10)
                pdf.multi_cell(0, 6, ascii_safe(note))
            pdf.ln(2)
        
        pdf.ln(5)
        
        # CO/CO2 Emission Notes
        fuel_name = self.input_params['fuel']
        if FUELS[fuel_name]['has_carbon']:
            pdf.set_font("Helvetica", 'B', 12)
            if FPDF_NEW_API:
                pdf.cell(0, 10, "CO and CO2 Emission Plots:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            else:
                pdf.cell(0, 10, "CO and CO2 Emission Plots:", ln=True)
                
            pdf.set_font("Helvetica", '', 12)
            notes = [
                "- Equilibrium calculations might not reflect real emissions due to kinetic limitations",
                "- CO may be underpredicted in rich conditions due to incomplete combustion",
                "- CO2 may be overpredicted in systems with rapid quenching preventing full oxidation",
                "- At extreme equivalence ratios, emissions are highly sensitive to kinetic factors"
            ]
            for note in notes:
                if FPDF_NEW_API:
                    pdf.cell(10)
                    pdf.multi_cell(0, 6, ascii_safe(note), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                else:
                    pdf.cell(10)
                    pdf.multi_cell(0, 6, ascii_safe(note))
            pdf.ln(2)
            
            pdf.ln(5)
        
        # Flame Speed Notes
        pdf.set_font("Helvetica", 'B', 12)
        if FPDF_NEW_API:
            pdf.cell(0, 10, "Flame Speed Plots:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.cell(0, 10, "Flame Speed Plots:", ln=True)
            
        pdf.set_font("Helvetica", '', 12)
        notes = [
            "- Zero flame speeds indicate non-convergence, likely outside flammability limits",
            "- At low temperatures or pressures, flames may be unstable or extinguish",
            "- Abrupt changes in plots may indicate numerical boundaries of model validity",
            f"- Current flame width setting: {self.advanced_settings['flame_width']['value']} m"
        ]
        for note in notes:
            if FPDF_NEW_API:
                pdf.cell(10)
                pdf.multi_cell(0, 6, ascii_safe(note), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            else:
                pdf.cell(10)
                pdf.multi_cell(0, 6, ascii_safe(note))
            pdf.ln(2)
        
        pdf.ln(5)
        
        # General Notes
        pdf.set_font("Helvetica", 'B', 12)
        if FPDF_NEW_API:
            pdf.cell(0, 10, "General Interpretation Guidelines:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.cell(0, 10, "General Interpretation Guidelines:", ln=True)
            
        pdf.set_font("Helvetica", '', 12)
        notes = [
            "- Flat areas at zero often indicate non-ignition or non-propagation conditions",
            "- Uniformly low/high values may represent model limitations in extreme regimes",
            "- Abrupt changes may indicate boundaries where solver converges/fails",
            "- Results at extreme conditions (T<900K, P<1atm, phi<0.5 or phi>2.0) may be unreliable"
        ]
        for note in notes:
            if FPDF_NEW_API:
                pdf.cell(10)
                pdf.multi_cell(0, 6, ascii_safe(note), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            else:
                pdf.cell(10)
                pdf.multi_cell(0, 6, ascii_safe(note))
            pdf.ln(2)
        
        # Add plots
        for plot_type, plot_label, file_path in self.plot_files:
            pdf.add_page()
            pdf.set_font("Helvetica", 'B', 16)
            
            # Use ASCII-safe plot labels
            safe_label = ascii_safe(plot_label)
            if plot_type == '3d':
                title = f"3D Plot: {safe_label}"
            else:  # contour
                title = f"Contour Plot: {safe_label}"
                
            if FPDF_NEW_API:
                pdf.cell(0, 10, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            else:
                pdf.cell(0, 10, title, ln=True)
                
            pdf.ln(5)
            
            # Plot description with ASCII replacements
            pdf.set_font("Helvetica", '', 12)
            if "Adiabatic_Temperature" in plot_label:
                desc = "Temperature achieved during adiabatic combustion"
            elif "Ignition_Delay" in plot_label:
                desc = "Time required for autoignition after heating"
            elif "Flame_Speed" in plot_label:
                desc = "Flame propagation speed in laminar conditions"
            elif "NOx_Emission" in plot_label:
                desc = "NOx emissions (ppm)"
            elif "CO_Emission" in plot_label:
                desc = "Carbon monoxide (CO) emissions (ppm)"
            elif "CO2_Emission" in plot_label:
                desc = "Carbon dioxide (CO2) emissions (ppm)"
            else:
                desc = "Combustion process result"
                
            if FPDF_NEW_API:
                pdf.multi_cell(0, 8, ascii_safe(desc), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            else:
                pdf.multi_cell(0, 8, ascii_safe(desc))
            pdf.ln(5)
            
            # Insert image
            try:
                # Scale image to page width
                with Image.open(file_path) as img:
                    w, h = img.size
                    aspect = h / w
                    max_width = 180  # mm
                    new_height = max_width * aspect
                    
                    # Check if height fits on page
                    if new_height > 250:  # mm
                        max_height = 250
                        new_width = max_height / aspect
                        pdf.image(file_path, x=(210 - new_width)/2, y=None, w=new_width)
                    else:
                        pdf.image(file_path, x=(210 - max_width)/2, y=None, w=max_width)
            except Exception as e:
                pdf.set_font("Helvetica", 'I', 10)
                error_msg = f"Error loading image: {str(e)}"
                if FPDF_NEW_API:
                    pdf.cell(0, 10, ascii_safe(error_msg), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                else:
                    pdf.cell(0, 10, ascii_safe(error_msg), ln=True)
        
        # Save PDF file
        pdf_file = os.path.join(self.results_dir, "combustion_analysis_report.pdf")
        pdf.output(pdf_file)
        
        return pdf_file

# Run the application
if __name__ == "__main__":
    root = tk.Tk()
    app = CombustionAnalyzerApp(root)
    root.mainloop()
