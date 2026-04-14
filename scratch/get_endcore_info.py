
import subprocess
import sys

def run_ssh_query(query):
    ssh_command = [
        "ssh", "-i", ".ssh\\umacore_key", "-o", "StrictHostKeyChecking=no",
        "umacore@20.212.105.13",
        f'docker exec umacore-postgres psql -U umacore -t -c "{query}"'
    ]
    try:
        result = subprocess.run(ssh_command, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e}"

if __name__ == "__main__":
    # Get circle_id for endcore
    circle_id = run_ssh_query("SELECT circle_id FROM clubs WHERE club_name ILIKE '%endcore%';")
    print(f"CIRCLE_ID: {circle_id}")
