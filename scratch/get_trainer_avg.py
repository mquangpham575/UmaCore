
import requests
import json
from datetime import datetime

def get_trainer_stats(trainer_id):
    # Get current month and year
    now = datetime.now()
    month = now.month
    year = now.year
    
    # API URL
    url = f"https://uma.moe/api/v4/rankings/monthly?month={month}&year={year}&page=0&limit=100&query={trainer_id}&circle_name={trainer_id}"
    
    print(f"🔍 Fetching stats for Trainer ID: {trainer_id} from uma.moe...")
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        

        # Check if we have data
        if not data.get('rankings'):
            print("❌ No data found for this Trainer ID.")
            return
            
        trainer = data['rankings'][0]
        name = trainer.get('trainer_name', 'Unknown')
        avg_daily = trainer.get('avg_daily', 0)
        total_gain = trainer.get('monthly_gain', 0)
        active_days = trainer.get('active_days', 0)
            
        print(f"✅ Trainer: {name}")
        print(f"   - Current Cumulative: {trainer.get('total_fans', 0):,}")
        print(f"   - Total Monthly Gain: {total_gain:,}")
        print(f"   - Active Days: {active_days}")
        print(f"   - Average Daily: {avg_daily:,.0f} fans/day")
        print(f"   - Current Club: {trainer.get('circle_name', 'None')}")

        
    except Exception as e:
        print(f"❌ Error fetching data: {e}")

if __name__ == "__main__":
    import sys
    trainer_id = "154984872830"
    if len(sys.argv) > 1:
        trainer_id = sys.argv[1]
    
    get_trainer_stats(trainer_id)
