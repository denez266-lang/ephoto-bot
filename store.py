import sqlite3, threading, time

DEFAULTS = {
    "welcome": "أهلاً! /effects لعرض التأثيرات، أو /search كلمة للبحث (بالإنجليزي). مثال: /search blood",
    "maintenance": "0",
    "notify_join": "1",
    "ban_notice": "1",
    "ban_msg": "🚫 تم حظرك من استخدام البوت.",
    "gate_on": "1",
    "gate_notify": "1",
    "gate_button": "1",
    "gate_msg": "🔐 للاستمرار لازم تشترك بالقنوات التالية أول، وبعدها اضغط تحقق.",
    "support": "للتواصل مع الدعم راسل الأدمن.",
    "report_url": "",
}


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.q("""CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, username TEXT,
                  joined REAL, last_seen REAL, banned INTEGER DEFAULT 0, inviter INTEGER)""")
        self.q("CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY)")
        self.q("CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT)")
        self.q("CREATE TABLE IF NOT EXISTS channels(id INTEGER PRIMARY KEY AUTOINCREMENT, ref TEXT UNIQUE, enabled INTEGER DEFAULT 1)")
        self.q("CREATE TABLE IF NOT EXISTS log(ts REAL, kind TEXT, uid INTEGER, text TEXT)")

    def q(self, sql, args=(), one=False, many=False):
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            if one:
                return cur.fetchone()
            if many:
                return cur.fetchall()
            return None

    # settings
    def get(self, k):
        r = self.q("SELECT v FROM settings WHERE k=?", (k,), one=True)
        return r[0] if r else DEFAULTS.get(k, "")

    def set(self, k, v):
        self.q("INSERT INTO settings(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))

    def on(self, k):
        return self.get(k) == "1"

    def toggle(self, k):
        self.set(k, "0" if self.on(k) else "1")

    # users
    def touch_user(self, uid, name, username, inviter=None):
        """Returns True if the user is new."""
        r = self.q("SELECT id FROM users WHERE id=?", (uid,), one=True)
        now = time.time()
        if r:
            self.q("UPDATE users SET name=?, username=?, last_seen=? WHERE id=?", (name, username, now, uid))
            return False
        self.q("INSERT INTO users(id,name,username,joined,last_seen,inviter) VALUES(?,?,?,?,?,?)",
               (uid, name, username, now, now, inviter))
        return True

    def all_user_ids(self, include_banned=False):
        sql = "SELECT id FROM users" + ("" if include_banned else " WHERE banned=0")
        return [r[0] for r in self.q(sql, many=True)]

    def is_banned(self, uid):
        r = self.q("SELECT banned FROM users WHERE id=?", (uid,), one=True)
        return bool(r and r[0])

    def set_ban(self, uid, flag):
        r = self.q("SELECT id FROM users WHERE id=?", (uid,), one=True)
        if not r:
            self.q("INSERT INTO users(id,name,username,joined,last_seen) VALUES(?,?,?,?,?)",
                   (uid, "", "", time.time(), time.time()))
        self.q("UPDATE users SET banned=? WHERE id=?", (1 if flag else 0, uid))

    def banned_list(self):
        return self.q("SELECT id,name,username FROM users WHERE banned=1", many=True)

    def stats(self):
        total = self.q("SELECT COUNT(*) FROM users", one=True)[0]
        day = self.q("SELECT COUNT(*) FROM users WHERE joined>?", (time.time() - 86400,), one=True)[0]
        active = self.q("SELECT COUNT(*) FROM users WHERE last_seen>?", (time.time() - 86400,), one=True)[0]
        banned = self.q("SELECT COUNT(*) FROM users WHERE banned=1", one=True)[0]
        return total, day, active, banned

    def invited_count(self, uid):
        return self.q("SELECT COUNT(*) FROM users WHERE inviter=?", (uid,), one=True)[0]

    # admins
    def admins(self):
        return [r[0] for r in self.q("SELECT id FROM admins", many=True)]

    def add_admin(self, uid):
        self.q("INSERT OR IGNORE INTO admins(id) VALUES(?)", (uid,))

    def del_admin(self, uid):
        self.q("DELETE FROM admins WHERE id=?", (uid,))

    # channels
    def channels(self):
        return self.q("SELECT id,ref,enabled FROM channels ORDER BY id", many=True)

    def add_channel(self, ref):
        self.q("INSERT OR IGNORE INTO channels(ref,enabled) VALUES(?,1)", (ref,))

    def toggle_channel(self, cid):
        self.q("UPDATE channels SET enabled=1-enabled WHERE id=?", (cid,))

    def del_channel(self, cid):
        self.q("DELETE FROM channels WHERE id=?", (cid,))

    def set_all_channels(self, flag):
        self.q("UPDATE channels SET enabled=?", (1 if flag else 0,))

    # log
    def log(self, kind, uid, text=""):
        self.q("INSERT INTO log(ts,kind,uid,text) VALUES(?,?,?,?)", (time.time(), kind, uid, text[:200]))

    def recent_log(self, n=20):
        return self.q("SELECT ts,kind,uid,text FROM log ORDER BY ts DESC LIMIT ?", (n,), many=True)
