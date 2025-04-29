# check_imports.py
import sys
import os
import importlib # Use importlib for cleaner checking

print("-" * 50)
print(f"Current Working Directory: {os.getcwd()}")
print("-" * 50)
print("Python sys.path (where Python looks for modules):")
for path in sys.path:
    print(f"- {path}")
print("-" * 50)
print("Checking potential module imports:")

# --- Modules to check ---
modules_to_check = [
    'history',
    'history.views',
    'nmif',
    'nmif.views',
    'nmif.history',
    'nmif.history.views',
    # Add any other potential paths you suspect
]

# --- Attempt imports ---
for module_name in modules_to_check:
    try:
        # Attempt to find the module without actually importing everything
        spec = importlib.util.find_spec(module_name)
        if spec:
            print(f"SUCCESS: Found module '{module_name}' (location: {spec.origin})")
        else:
            # This case might occur if it's a namespace package or something unusual
             print(f"INFO: Could find spec but no origin for '{module_name}'. Might be importable.")
             # Optionally try a full import here if needed, but find_spec is safer
             # importlib.import_module(module_name)
             # print(f"SUCCESS: Imported module '{module_name}'")

    except ImportError:
        print(f"FAILED: Could not find or import module '{module_name}'")
    except Exception as e:
        print(f"ERROR checking module '{module_name}': {e}")

print("-" * 50)
print("Diagnosis Help:")
print("- Check if your project's root directory (containing 'manage.py') is listed in sys.path.")
print("- If not, you might need to adjust your PYTHONPATH environment variable or how you run pytest.")
print("- Ensure the directories you are trying to import from (e.g., 'nmif', 'history') contain an '__init__.py' file.")
print("- Based on the SUCCESS/FAILED messages above, adjust the 'from ... import ...' lines in your test file.")
print("-" * 50)

