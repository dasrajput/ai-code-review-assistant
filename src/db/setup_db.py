import sqlite3

conn = sqlite3.connect('src/db/reviews.db')
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file TEXT,
        suggestion TEXT,
        timestamp TEXT
    )
''')
conn.commit()
conn.close()