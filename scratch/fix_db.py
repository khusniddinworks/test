import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def fix_packages():
    # Barcha kerakli paketlar ro'yxati
    needed_packages = [
        {"key_name": "standard", "display_name": "Standart Paket", "price": 1150},
        {"key_name": "comfort", "display_name": "Komfort Paket", "price": 1300},
        {"key_name": "lux", "display_name": "LUX Paket", "price": 1550},
        {"key_name": "lux_premium", "display_name": "LUX Premium", "price": 1650},
        {"key_name": "special_14day", "display_name": "14 Kunlik (4 kishilik)", "price": 1390},
        {"key_name": "special_14day_3", "display_name": "14 Kunlik (3 kishilik)", "price": 1490},
        {"key_name": "special_14day_2", "display_name": "14 Kunlik (2 kishilik)", "price": 1650}
    ]
    
    print("Checking packages...")
    for pkg in needed_packages:
        try:
            res = supabase.table("packages").select("*").eq("key_name", pkg['key_name']).execute()
            if not res.data:
                supabase.table("packages").insert(pkg).execute()
                print(f"Added: {pkg['display_name']}")
            else:
                # Agar bor bo'lsa, nomini yangilab qo'yamiz (chiroyli chiqishi uchun)
                supabase.table("packages").update({"display_name": pkg['display_name']}).eq("key_name", pkg['key_name']).execute()
                print(f"Updated/Exists: {pkg['display_name']}")
        except Exception as e:
            print(f"Error ({pkg['key_name']}): {str(e)}")
            
    # Yakuniy holatni tekshirish
    final_res = supabase.table("packages").select("*").execute()
    print(f"Total packages in DB: {len(final_res.data)}")

if __name__ == "__main__":
    fix_packages()
