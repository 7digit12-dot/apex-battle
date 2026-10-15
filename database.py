from pymongo import MongoClient
import certifi
# MongoDB Atlas cluster connection URI
MONGO_URI = "mongodb+srv://7digit12_db_user:3tV6K6AJUcaH8I56@cluster0.cqfkdwg.mongodb.net/?appName=Cluster0"

try:
    print("Initiating MongoDB Atlas connection...")
    client = MongoClient(
    MONGO_URI,
    tlsCAFile=certifi.where(),
    tlsAllowInvalidCertificates=True
)

    # Ping the cluster to verify connectivity
    client.admin.command("ping")
    print("Database connection successfully established.")
    
    # Initialize database and collections
    db = client["esports_arena"]
    users_collection = db["users"]
    tournaments_collection = db["tournaments"]
    matches_collection = db["matches"]
    
    
    print("Collections initialized: users, tournaments, matches.")

except Exception as error:
    print(f"Database connection failed: {error}")