import sys
import database
import models

if "--force" not in sys.argv:
    print("Warning: Running init_db.py will drop and recreate all database tables.")
    print("Pass '--force' to confirm execution (e.g. 'python init_db.py --force').")
    sys.exit(0)

print("Dropping existing tables...")
models.Base.metadata.drop_all(bind=database.engine)

print("Creating fresh tables...")
models.Base.metadata.create_all(bind=database.engine)

print("Database reset complete.")