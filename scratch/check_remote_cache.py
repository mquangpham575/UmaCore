import subprocess

def run_ssh_cmd(cmd):
    ssh_command = [
        "ssh", "-i", ".ssh\\umacore_key", "-o", "StrictHostKeyChecking=no",
        "umacore@20.212.105.13",
        cmd
    ]
    try:
        result = subprocess.run(ssh_command, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e}\nStdout: {e.stdout if hasattr(e, 'stdout') else ''}\nStderr: {e.stderr if hasattr(e, 'stderr') else ''}"

if __name__ == "__main__":
    print("Listing remote cache files:")
    print(run_ssh_cmd("docker exec umacore-bot ls -la /app/cache/leaderboards"))
