from django.db import connection
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

def check_columns():
    with connection.cursor() as cursor:
        tables = {
            'expenses_custodysettlement': 'is_posted',
            'sales_salesreturnline': 'cost',
            'sales_salesreturn': 'discount_amount',
            'purchases_purchasereturn': 'discount_amount'
        }
        for table, column in tables.items():
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in cursor.fetchall()]
            exists = column in columns
            print(f"Table {table}: column {column} exists: {exists}")
            if not exists:
                print(f"  Available columns: {columns}")

if __name__ == "__main__":
    check_columns()
