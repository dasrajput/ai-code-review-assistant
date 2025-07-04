import sqlite3
import json
import sys

# Get data from n8n (passed as JSON string)
data = json.loads(sys.argv[1])
file_name = data.get("files", [{}])[0].get("filename", "unknown.py")
suggestion = "Sample review"
timestamp = data.get("now", "")

# Connect to database
conn = sqlite3.connect('src/db/reviews.db')
cursor = conn.cursor()
cursor.execute('INSERT INTO reviews (file, suggestion, timestamp) VALUES (?, ?, ?)', (file_name, suggestion, timestamp))
conn.commit()
conn.close()