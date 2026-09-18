# Launcher for the JobAgent application-email monitor; the real script lives in the JobAgent workspace.
import runpy, sys
sys.path.insert(0, r"C:\Users\monte\JobAgent\tools")
runpy.run_path(r"C:\Users\monte\JobAgent\tools\app_email_monitor.py", run_name="__main__")
