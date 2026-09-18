# Launcher for the JobAgent tracker snapshot; the real script lives in the JobAgent workspace.
import runpy, sys
sys.path.insert(0, r"C:\Users\monte\JobAgent\tools")
runpy.run_path(r"C:\Users\monte\JobAgent\tools\tracker_report.py", run_name="__main__")
