from AppKit import NSWorkspace

def get_active_window_info():
    """
    Returns the name of the active application.
    """
    workspace = NSWorkspace.sharedWorkspace()
    active_app = workspace.frontmostApplication()
    
    if active_app:
        return active_app.localizedName()
    return "Unknown"
