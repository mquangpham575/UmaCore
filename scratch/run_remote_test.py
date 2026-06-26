import subprocess

def run_ssh_cmd_with_stdin(file_path):
    # Read the local script file
    with open(file_path, "r", encoding="utf-8") as f:
        script_content = f.read()
        
    ssh_command = [
        "ssh", "-i", ".ssh\\umacore_key", "-o", "StrictHostKeyChecking=no",
        "umacore@20.212.105.13",
        "docker exec -i umacore-bot python"
    ]
    try:
        result = subprocess.run(
            ssh_command,
            input=script_content,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e}\nStdout: {e.stdout if hasattr(e, 'stdout') else ''}\nStderr: {e.stderr if hasattr(e, 'stderr') else ''}"

if __name__ == "__main__":
    print("Running rename verification test script on remote bot container...")
    print(run_ssh_cmd_with_stdin("scratch/test_club_rename.py"))
