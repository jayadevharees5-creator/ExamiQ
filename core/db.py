import os
import json
import time
import hashlib
import secrets
import hmac
from pathlib import Path
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
# Ensure robust DNS resolution for MongoDB Atlas SRV records
try:
    import dns.resolver
    resolver = dns.resolver.Resolver(configure=True)
    # If system resolver has no nameservers, append public fallbacks
    if not resolver.nameservers:
        resolver.nameservers = ['8.8.8.8', '1.1.1.1', '8.8.4.4']
    dns.resolver.default_resolver = resolver
except Exception as _dns_err:
    pass

import pymongo
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

class DatabaseManager:
    """
    Manages MongoDB connection, authentication, and persistence for QuizForge.
    Supports real MongoDB connections (local & MongoDB Atlas) with transparent
    offline fallback persistence in data/db_store.json.
    """

    def __init__(self, mongo_uri: str = "mongodb://localhost:27017/", db_name: str = "question_generator_db"):
        self.mongo_uri = mongo_uri.strip()
        self.db_name = db_name.strip()
        self.client: Optional[pymongo.MongoClient] = None
        self.db = None
        self.users_col = None
        self.papers_col = None
        self.materials_col = None
        self.is_connected = False
        self.connection_error = ""
        
        # Local persistent fallback file
        self.fallback_file = Path(__file__).resolve().parent.parent / "data" / "db_store.json"
        self.fallback_file.parent.mkdir(parents=True, exist_ok=True)
        self._init_fallback_store()

        # Connect to MongoDB
        self.connect()

    def _init_fallback_store(self):
        """Initializes the local fallback JSON store if not exists."""
        if not self.fallback_file.exists():
            initial_data = {
                "users": [],
                "question_papers": [],
                "study_materials": []
            }
            self.fallback_file.write_text(json.dumps(initial_data, indent=2), encoding="utf-8")

    def _read_fallback(self) -> Dict[str, Any]:
        """Reads local fallback store safely."""
        try:
            if self.fallback_file.exists():
                return json.loads(self.fallback_file.read_text(encoding="utf-8"))
        except Exception as e:
            print("Error reading fallback db store:", e)
        return {"users": [], "question_papers": [], "study_materials": []}

    def is_admin(self, username: str) -> bool:
        """Return True if the given username has role 'admin'."""
        try:
            if not self.is_connected or self.users_col is None:
                # fallback to JSON store
                data = self._read_fallback()
                for u in data.get("users", []):
                    if u.get("username") == username and u.get("role") == "admin":
                        return True
                return False
            user = self.users_col.find_one({"username": username})
            return bool(user and user.get("role") == "admin")
        except Exception as e:
            print(f"[MongoDB] admin check error: {e}")
            return False

    def _write_fallback(self, data: Dict[str, Any]):
        """Writes to local fallback store safely."""
        try:
            self.fallback_file.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            print("Error writing fallback db store:", e)

    def connect(self, uri: Optional[str] = None, db_name: Optional[str] = None) -> bool:
        """
        Attempts to establish a connection to MongoDB.
        """
        if uri:
            self.mongo_uri = uri.strip()
        if db_name:
            self.db_name = db_name.strip()

        try:
            # Connect to MongoDB with adequate timeout for Atlas cluster discovery and TLS handshake
            self.client = pymongo.MongoClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=20000,
                connectTimeoutMS=20000,
                socketTimeoutMS=20000
            )
            # Check connection with admin ping
            self.client.admin.command('ping')
            
            self.db = self.client[self.db_name]
            self.users_col = self.db["users"]
            self.papers_col = self.db["question_papers"]
            self.materials_col = self.db["study_materials"]
            
            # Ensure indexes
            self.users_col.create_index("username", unique=True)
            self.papers_col.create_index("id", unique=True)
            self.papers_col.create_index("created_by")
            self.materials_col.create_index("id", unique=True)
            self.materials_col.create_index("created_by")
            
            self.is_connected = True
            self.connection_error = ""
            print(f"[MongoDB] Successfully connected to MongoDB: {self.db_name} at {self._safe_uri()}")
            
            # Seed default accounts in MongoDB and sync fallback users
            self._seed_default_users()
            self._sync_fallback_users_to_mongo()
            return True

        except (ConnectionFailure, ServerSelectionTimeoutError, Exception) as e:
            self.is_connected = False
            self.connection_error = str(e)
            print(f"[MongoDB] Notice: Could not connect to MongoDB server ({self._safe_uri()}). Running in resilient fallback mode.")
            # Seed default accounts in local fallback
            self._seed_default_users()
            return False

    def _safe_uri(self) -> str:
        """Returns URI with hidden credentials for safe logging."""
        if "@" in self.mongo_uri:
            parts = self.mongo_uri.split("@")
            scheme = parts[0].split("://")[0]
            return f"{scheme}://****:****@{parts[1]}"
        return self.mongo_uri

    def _sync_fallback_users_to_mongo(self):
        """Syncs any locally registered users in the fallback file into MongoDB Atlas."""
        if not self.is_connected or self.users_col is None:
            return
        try:
            store = self._read_fallback()
            for u in store.get("users", []):
                uname = u.get("username", "").strip().lower()
                if uname:
                    self.users_col.update_one(
                        {"username": uname},
                        {"$setOnInsert": u},
                        upsert=True
                    )
        except Exception as e:
            print("[MongoDB] User sync notice:", e)

    @staticmethod
    def _hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
        """Hashes password with cryptographic salt using SHA-256."""
        if not salt:
            salt = secrets.token_hex(16)
        hash_obj = hashlib.sha256((password + salt).encode('utf-8'))
        return hash_obj.hexdigest(), salt

    @staticmethod
    def _verify_password(password: str, expected_hash: str, salt: str = "") -> bool:
        """Verifies password using timing-safe comparison with SHA-256 or bcrypt."""
        if not expected_hash:
            return False
        calc_hash = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
        if hmac.compare_digest(calc_hash, expected_hash):
            return True
        if expected_hash.startswith(("$2a$", "$2b$", "$2y$")):
            try:
                import bcrypt
                return bcrypt.checkpw(password.encode("utf-8")[:72], expected_hash.encode("utf-8"))
            except Exception:
                return False
        return False

    def _seed_default_users(self):
        """Seeds default Admin and User accounts, ensuring Admin password is synchronised from .env."""
        admin_pwd = os.getenv("ADMIN_PASSWORD", "admin123")
        admin_hash, admin_salt = self._hash_password(admin_pwd)

        user_pwd = "user123"
        user_hash, user_salt = self._hash_password(user_pwd)

        admin_doc = {
            "username": "admin",
            "password_hash": admin_hash,
            "salt": admin_salt,
            "role": "admin",
            "full_name": "System Administrator",
            "department": "Administration",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        user_doc = {
            "username": "user",
            "password_hash": user_hash,
            "salt": user_salt,
            "role": "user",
            "full_name": "Standard User",
            "department": "Academics",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        if self.is_connected and self.users_col is not None:
            try:
                # Sync admin credentials directly from environment
                self.users_col.update_one(
                    {"username": "admin"},
                    {"$set": {"password_hash": admin_hash, "salt": admin_salt, "role": "admin"}},
                    upsert=True
                )
                self.users_col.update_one(
                    {"username": "user"},
                    {"$setOnInsert": user_doc},
                    upsert=True
                )
            except Exception as e:
                print("MongoDB seed error:", e)
        else:
            store = self._read_fallback()
            # Ensure admin password reflects env
            admin_found = False
            for u in store.get("users", []):
                if u.get("username", "").lower() == "admin":
                    u["password_hash"] = admin_hash
                    u["salt"] = admin_salt
                    admin_found = True
                    break
            if not admin_found:
                store["users"].append(admin_doc)

            if not any(u.get("username", "").lower() == "user" for u in store.get("users", [])):
                store["users"].append(user_doc)
            self._write_fallback(store)

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Retrieves a user document by username."""
        username = username.strip().lower()
        if self.is_connected and self.users_col is not None:
            try:
                doc = self.users_col.find_one({"username": username})
                if doc:
                    doc["_id"] = str(doc.get("_id", ""))
                    return doc
            except Exception as e:
                print("MongoDB get_user error:", e)

        # Fallback store lookup
        store = self._read_fallback()
        for u in store.get("users", []):
            if u["username"].lower() == username:
                return dict(u)
        return None

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Authenticates an Admin or User by username and password.
        For the admin account, authentication is directly verified against ADMIN_PASSWORD from .env.
        Returns user metadata dictionary if valid, None otherwise.
        """
        uname = username.strip().lower()
        if uname == "admin":
            env_admin_pwd = os.getenv("ADMIN_PASSWORD", "admin123")
            if password == env_admin_pwd:
                user = self.get_user("admin") or {}
                return {
                    "username": "admin",
                    "role": "admin",
                    "full_name": user.get("full_name", "System Administrator"),
                    "department": user.get("department", "Administration"),
                    "created_at": user.get("created_at", "")
                }
            return None

        user = self.get_user(uname)
        if not user:
            return None

        salt = user.get("salt", "")
        expected_hash = user.get("password_hash", "")

        if self._verify_password(password, expected_hash, salt):
            return {
                "username": user["username"],
                "role": user.get("role", "user"),
                "full_name": user.get("full_name", user["username"]),
                "department": user.get("department", ""),
                "created_at": user.get("created_at", "")
            }
        return None

    def register_user(self, username: str, password: str, role: str = "user", full_name: str = "", department: str = "") -> Dict[str, Any]:
        """
        Registers a new Admin or User account and persists immediately to MongoDB Atlas & fallback store.
        """
        username = username.strip().lower()
        if not username or len(username) < 3:
            return {"success": False, "error": "Username must be at least 3 characters."}
        if not password or len(password) < 4:
            return {"success": False, "error": "Password must be at least 4 characters."}

        role = role.lower() if role.lower() in ("admin", "user") else "user"
        if not full_name:
            full_name = username.capitalize()

        if self.get_user(username):
            return {"success": False, "error": f"Username '{username}' is already registered."}

        pwd_hash, salt = self._hash_password(password)
        new_user = {
            "username": username,
            "password_hash": pwd_hash,
            "salt": salt,
            "role": role,
            "full_name": full_name,
            "department": department,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        # 1. Save to local fallback store
        store = self._read_fallback()
        if not any(u["username"].lower() == username for u in store.get("users", [])):
            store["users"].append(new_user)
            self._write_fallback(store)

        # 2. Save directly to MongoDB Atlas
        if self.is_connected and self.users_col is not None:
            try:
                self.users_col.insert_one(new_user.copy())
            except Exception as e:
                print("MongoDB registration error:", e)

        return {
            "success": True,
            "user": {
                "username": username,
                "role": role,
                "full_name": full_name,
                "department": department
            }
        }

    def save_question_paper(self, paper: Dict[str, Any], username: Optional[str] = None) -> bool:
        """
        Persists an examination paper record into MongoDB (or fallback), tagged with the owner's username.
        """
        paper_id = paper.get("id")
        if not paper_id:
            paper_id = f"doc_{int(time.time()*1000)}"
            paper["id"] = paper_id

        if username:
            paper["created_by"] = username.strip().lower()
        elif "created_by" not in paper:
            paper["created_by"] = "anonymous"

        if self.is_connected and self.papers_col is not None:
            try:
                # Upsert paper in MongoDB
                self.papers_col.update_one(
                    {"id": paper_id},
                    {"$set": paper},
                    upsert=True
                )
            except Exception as e:
                print("MongoDB save_question_paper error:", e)

        # Fallback store
        store = self._read_fallback()
        existing_idx = next((i for i, p in enumerate(store.get("question_papers", [])) if p.get("id") == paper_id), -1)
        if existing_idx >= 0:
            store["question_papers"][existing_idx] = paper
        else:
            store["question_papers"].insert(0, paper)
        self._write_fallback(store)
        return True

    def get_all_question_papers(self, username: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieves examination papers, strictly isolated by username when provided.
        """
        target_user = username.strip().lower() if username else None

        if self.is_connected and self.papers_col is not None:
            try:
                query = {}
                if target_user:
                    query = {"created_by": target_user}
                docs = list(self.papers_col.find(query).sort("_id", -1))
                for d in docs:
                    d["_id"] = str(d.get("_id", ""))
                return docs
            except Exception as e:
                print("MongoDB get_all_question_papers error:", e)

        store = self._read_fallback()
        papers = store.get("question_papers", [])
        if target_user:
            papers = [p for p in papers if (p.get("created_by") or "").strip().lower() == target_user]
        return papers

    def get_paper_by_id(self, paper_id: str, username: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieves a single question paper by ID, optionally verifying ownership.
        """
        if self.is_connected and self.papers_col is not None:
            try:
                query = {"id": paper_id}
                if username and username != "admin":
                    query["created_by"] = username.strip().lower()
                doc = self.papers_col.find_one(query)
                if doc:
                    doc["_id"] = str(doc.get("_id", ""))
                    return doc
            except Exception as e:
                print("MongoDB get_paper_by_id error:", e)

        store = self._read_fallback()
        for p in store.get("question_papers", []):
            if p.get("id") == paper_id:
                if username and username != "admin":
                    if (p.get("created_by") or "").strip().lower() != username.strip().lower():
                        continue
                return dict(p)
        return None

    def delete_question_paper(self, paper_id: str, username: Optional[str] = None) -> bool:
        """
        Deletes a question paper by ID, ensuring user ownership.
        """
        target_user = username.strip().lower() if username and username != "admin" else None

        if self.is_connected and self.papers_col is not None:
            try:
                query = {"id": paper_id}
                if target_user:
                    query["created_by"] = target_user
                self.papers_col.delete_one(query)
            except Exception as e:
                print("MongoDB delete_question_paper error:", e)

        store = self._read_fallback()
        store["question_papers"] = [
            p for p in store.get("question_papers", [])
            if not (p.get("id") == paper_id and (target_user is None or (p.get("created_by") or "").strip().lower() == target_user))
        ]
        self._write_fallback(store)
        return True
    def get_all_users(self) -> List[Dict[str, Any]]:
        """
        Returns all registered users with activity statistics (paper count, question count).
        Used by the admin dashboard.
        """
        users = []

        if self.is_connected and self.users_col is not None:
            try:
                user_docs = list(self.users_col.find({}))
                for u in user_docs:
                    uname = u.get("username", "")
                    paper_count = 0
                    question_count = 0
                    try:
                        papers = list(self.papers_col.find({"created_by": uname}))
                        paper_count = len(papers)
                        question_count = sum(len(p.get("questions", [])) for p in papers)
                    except Exception:
                        pass

                    users.append({
                        "username": uname,
                        "role": u.get("role", "user"),
                        "full_name": u.get("full_name", uname),
                        "department": u.get("department", ""),
                        "created_at": u.get("created_at", ""),
                        "papers_count": paper_count,
                        "questions_count": question_count
                    })
                return users
            except Exception as e:
                print("MongoDB get_all_users error:", e)

        # Fallback store
        store = self._read_fallback()
        for u in store.get("users", []):
            uname = u.get("username", "")
            papers = [p for p in store.get("question_papers", []) if (p.get("created_by") or "") == uname]
            question_count = sum(len(p.get("questions", [])) for p in papers)
            users.append({
                "username": uname,
                "role": u.get("role", "user"),
                "full_name": u.get("full_name", uname),
                "department": u.get("department", ""),
                "created_at": u.get("created_at", ""),
                "papers_count": len(papers),
                "questions_count": question_count
            })
        return users

    def delete_user(self, username: str, requesting_admin: str) -> Dict[str, Any]:
        """
        Deletes a user account and all their generated papers.
        Only admins can delete users. Admins cannot delete themselves.
        """
        username = username.strip().lower()
        requesting_admin = requesting_admin.strip().lower()

        if username == requesting_admin:
            return {"success": False, "error": "You cannot delete your own admin account."}

        # Verify the target user exists
        target_user = self.get_user(username)
        if not target_user:
            return {"success": False, "error": f"User '{username}' not found."}

        # Prevent deletion of the primary 'admin' account
        if username == "admin":
            return {"success": False, "error": "The primary admin account cannot be deleted."}

        # Delete from MongoDB
        if self.is_connected:
            try:
                self.users_col.delete_one({"username": username})
                self.papers_col.delete_many({"created_by": username})
            except Exception as e:
                print("MongoDB delete_user error:", e)

        # Delete from fallback store
        store = self._read_fallback()
        store["users"] = [u for u in store.get("users", []) if u.get("username", "").lower() != username]
        store["question_papers"] = [p for p in store.get("question_papers", []) if (p.get("created_by") or "").lower() != username]
        self._write_fallback(store)

        return {"success": True, "message": f"User '{username}' and all their data have been deleted."}

    def promote_to_admin(self, username: str, requesting_admin: str) -> Dict[str, Any]:
        """
        Promotes a user to admin role. This is a one-way operation — admins cannot be demoted.
        """
        username = username.strip().lower()
        requesting_admin = requesting_admin.strip().lower()

        target_user = self.get_user(username)
        if not target_user:
            return {"success": False, "error": f"User '{username}' not found."}

        if target_user.get("role") == "admin":
            return {"success": False, "error": f"'{username}' is already an admin."}

        # Update in MongoDB
        if self.is_connected and self.users_col is not None:
            try:
                self.users_col.update_one({"username": username}, {"$set": {"role": "admin"}})
            except Exception as e:
                print("MongoDB promote_to_admin error:", e)

        # Update in fallback store
        store = self._read_fallback()
        for u in store.get("users", []):
            if u.get("username", "").lower() == username:
                u["role"] = "admin"
                break
        self._write_fallback(store)

        return {"success": True, "message": f"'{username}' has been promoted to admin."}

    def reset_password(self, username: str, new_password: str) -> Dict[str, Any]:
        """
        Resets a user's password. Used for the forgot-password flow.
        Admin account cannot be reset here — it can only be changed via .env.
        """
        username = username.strip().lower()

        if username == "admin":
            return {
                "success": False,
                "error": "The admin password cannot be changed via forgot password. It can only be changed in the server .env file."
            }

        if not new_password or len(new_password) < 4:
            return {"success": False, "error": "New password must be at least 4 characters."}

        target_user = self.get_user(username)
        if not target_user:
            return {"success": False, "error": f"Username '{username}' not found. Please check and try again."}

        pwd_hash, salt = self._hash_password(new_password)

        # Update in MongoDB
        if self.is_connected and self.users_col is not None:
            try:
                self.users_col.update_one(
                    {"username": username},
                    {"$set": {"password_hash": pwd_hash, "salt": salt}}
                )
            except Exception as e:
                print("MongoDB reset_password error:", e)

        # Update in fallback store
        store = self._read_fallback()
        for u in store.get("users", []):
            if u.get("username", "").lower() == username:
                u["password_hash"] = pwd_hash
                u["salt"] = salt
                break
        self._write_fallback(store)

        return {"success": True, "message": "Password has been reset successfully. You can now sign in with your new password."}

    # -------------------------------------------------------------
    # Processed Study Materials Operations (Strictly Isolated by User)
    # -------------------------------------------------------------
    def save_study_material(self, material_data: Dict[str, Any], username: str) -> bool:
        """
        Saves a processed study material strictly tagged with the user's username.
        """
        uname = username.strip().lower()
        material_data["created_by"] = uname

        if self.is_connected and self.materials_col is not None:
            try:
                self.materials_col.update_one(
                    {"id": material_data["id"]},
                    {"$set": material_data},
                    upsert=True
                )
            except Exception as e:
                print("MongoDB save_study_material error:", e)

        store = self._read_fallback()
        if "study_materials" not in store:
            store["study_materials"] = []
        store["study_materials"] = [m for m in store["study_materials"] if m.get("id") != material_data["id"]]
        store["study_materials"].append(material_data)
        self._write_fallback(store)
        return True

    def get_user_study_materials(self, username: str) -> List[Dict[str, Any]]:
        """
        Returns all study materials processed by this user alone.
        Excludes heavy pages_data when listing.
        """
        uname = username.strip().lower()
        materials = []

        if self.is_connected and self.materials_col is not None:
            try:
                docs = list(self.materials_col.find({"created_by": uname}, {"pages_data": 0}))
                for d in docs:
                    d["_id"] = str(d.get("_id", ""))
                    materials.append(d)
                materials.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                return materials
            except Exception as e:
                print("MongoDB get_user_study_materials error:", e)

        store = self._read_fallback()
        for m in store.get("study_materials", []):
            if (m.get("created_by") or "").strip().lower() == uname:
                copy_m = {k: v for k, v in m.items() if k != "pages_data"}
                materials.append(copy_m)

        materials.reverse()
        return materials

    def get_study_material_by_id(self, material_id: str, username: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves complete study material (including pages_data) for this user alone.
        """
        uname = username.strip().lower()

        if self.is_connected and self.materials_col is not None:
            try:
                doc = self.materials_col.find_one({"id": material_id, "created_by": uname})
                if doc:
                    doc["_id"] = str(doc.get("_id", ""))
                    return doc
            except Exception as e:
                print("MongoDB get_study_material_by_id error:", e)

        store = self._read_fallback()
        for m in store.get("study_materials", []):
            if m.get("id") == material_id and (m.get("created_by") or "").strip().lower() == uname:
                return dict(m)
        return None

    def delete_study_material(self, material_id: str, username: str) -> bool:
        """
        Deletes a study material belonging to this user alone.
        """
        uname = username.strip().lower()

        if self.is_connected and self.materials_col is not None:
            try:
                self.materials_col.delete_one({"id": material_id, "created_by": uname})
            except Exception as e:
                print("MongoDB delete_study_material error:", e)

        store = self._read_fallback()
        if "study_materials" in store:
            store["study_materials"] = [m for m in store["study_materials"] if not (m.get("id") == material_id and (m.get("created_by") or "").strip().lower() == uname)]
            self._write_fallback(store)
        return True

# Global singleton instance
db_manager = DatabaseManager(
    mongo_uri=os.getenv("MONGODB_URI") or os.getenv("MONGO_URI", "mongodb://localhost:27017/"),
    db_name=os.getenv("MONGO_DB_NAME", "question_generator_db")
)
