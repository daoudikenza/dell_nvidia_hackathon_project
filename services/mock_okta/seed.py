"""
Seeds a realistic engineering org into mock-Okta.

The seed IS the demo. Over-provisioning is planted deliberately so the agent
has real findings to surface on stage. Every planted problem below is a thing
that happens at every real company.
"""
import json, random, datetime as dt, pathlib

random.seed(42)                      # reproducible demos
NOW = dt.datetime(2026, 9, 12, 9, 0, 0)
OUT = pathlib.Path(__file__).parent / "org.json"

TEAMS = {
    "billing":   ["packages/features/ee/billing", "packages/prisma", "apps/api/v2"],
    "bookings":  ["packages/features/bookings", "apps/web/modules/bookings"],
    "platform":  ["packages/lib", "packages/ui", "apps/web"],
    "app-store": ["packages/app-store"],
    "infra":     [".github/workflows", "docker", "infra"],
}

# group -> (description, sensitivity)  sensitivity: 0 routine, 1 elevated, 2 production
GROUPS = {
    "eng-billing":         ("Billing service engineers", 0),
    "eng-bookings":        ("Bookings service engineers", 0),
    "eng-platform":        ("Platform/shared library engineers", 0),
    "eng-appstore":        ("App store integrations", 0),
    "eng-infra":           ("Infrastructure engineers", 1),
    "db-staging-read":     ("Read staging Postgres", 0),
    "db-prod-read":        ("Read production Postgres", 1),
    "db-prod-write":       ("WRITE production Postgres", 2),
    "vault-billing-read":  ("Read vault:secret/billing/* (test)", 0),
    "vault-billing-admin": ("Admin vault:secret/billing/* incl. live keys", 2),
    "deploy-staging":      ("Deploy to staging", 0),
    "deploy-prod":         ("Deploy to production", 2),
    "infra-admin":         ("Full infrastructure admin", 2),
    "grafana-billing":     ("Grafana billing dashboards", 0),
    "sentry-eng":          ("Sentry error tracking", 0),
    "datadog-eng":         ("Datadog APM", 0),
    "jira-eng":            ("Jira engineering projects", 0),
    "figma-viewer":        ("Figma design files (read)", 0),
    "analytics-dashboard": ("Product analytics warehouse", 1),
    "pagerduty-oncall":    ("PagerDuty on-call rotation", 1),
}

FIRST = ["Sarah","Marcus","Priya","Tom","Ana","Wei","Jonas","Leila","Diego","Ruth",
         "Ben","Yuki","Omar","Nina","Cole","Fatima","Ivan","Grace","Hugo","Mei",
         "Raj","Ellie","Sven","Aisha","Noah","Zara","Liam","Ida","Kofi","Petra",
         "Alex","Mira","Theo","Lena","Sam","Iris","Dan","Nora","Emil","Tess"]
LAST = ["Chen","Okafor","Novak","Silva","Haddad","Ibrahim","Larsson","Moreau","Reyes",
        "Kowalski","Bianchi","Yamada","Nkemdirim","Petrov","Dubois","Ahmed","Costa",
        "Fischer","Rossi","Andersen"]

def iso(d): return d.strftime("%Y-%m-%dT%H:%M:%S.000Z")

users, groups, memberships, logs = [], [], [], []

for gid,(desc,sens) in GROUPS.items():
    groups.append({"id": f"grp{abs(hash(gid))%10**8:08d}", "profile":
                   {"name": gid, "description": desc},
                   "_sensitivity": sens, "type": "OKTA_GROUP"})
GID = {g["profile"]["name"]: g["id"] for g in groups}

team_names = list(TEAMS)
for i in range(40):
    team = team_names[i % len(team_names)]
    fn, ln = FIRST[i], LAST[i % len(LAST)]
    uid = f"00u{i:08d}"
    users.append({
        "id": uid, "status": "ACTIVE",
        "created": iso(NOW - dt.timedelta(days=random.randint(40, 1400))),
        "profile": {"firstName": fn, "lastName": ln,
                    "email": f"{fn.lower()}.{ln.lower()}@cal.example.com",
                    "login": f"{fn.lower()}.{ln.lower()}@cal.example.com",
                    "title": "Software Engineer", "department": team},
        # Okta Verify enrollment — the agent gates grants on this
        "_factors": [{"factorType":"push","provider":"OKTA","status":"ACTIVE"}]
                    if i % 13 else [],          # ~3 users NOT enrolled
    })
    base = {"billing":"eng-billing","bookings":"eng-bookings","platform":"eng-platform",
            "app-store":"eng-appstore","infra":"eng-infra"}[team]
    tenure = random.randint(30, 1100)
    give = [base, "db-staging-read", "deploy-staging", "jira-eng", "sentry-eng"]
    if team == "billing":   give += ["grafana-billing", "vault-billing-read"]
    if team == "bookings":  give += ["grafana-billing"]
    if team == "infra":     give += ["datadog-eng", "pagerduty-oncall"]
    # privilege creep: the longer you have been here, the more you have collected
    if tenure > 400:  give += ["figma-viewer"]
    if tenure > 700:  give += ["datadog-eng", "db-prod-read"]
    if tenure > 950:  give += ["analytics-dashboard"]
    for g in dict.fromkeys(give):
        memberships.append({"userId": uid, "groupId": GID[g],
                            "granted": iso(NOW - dt.timedelta(days=random.randint(20, tenure)))})

U = {u["id"]: u for u in users}
def grant(uid, g, days_ago):
    memberships.append({"userId": uid, "groupId": GID[g],
                        "granted": iso(NOW - dt.timedelta(days=days_ago))})

# ---- PLANTED PROBLEM 1: prod write access, never used (the headline finding)
STALE_PROD = ["00u00000003", "00u00000011", "00u00000027"]
for uid in STALE_PROD:
    grant(uid, "db-prod-write", 210)

# ---- PLANTED PROBLEM 2: changed teams, kept the old group (privilege creep)
MOVED = {"00u00000007": "eng-bookings", "00u00000019": "eng-appstore"}
for uid, old in MOVED.items():
    grant(uid, old, 430)

# ---- PLANTED PROBLEM 3: service account with full infra admin, dormant
users.append({"id":"00usvc00001","status":"ACTIVE","created":iso(NOW-dt.timedelta(days=980)),
              "profile":{"firstName":"ci","lastName":"runner",
                         "email":"ci-runner@cal.example.com","login":"ci-runner@cal.example.com",
                         "title":"Service Account","department":"infra"},"_factors":[]})
grant("00usvc00001","infra-admin",980)
grant("00usvc00001","deploy-prod",980)

# ---- PLANTED PROBLEM 4: vault admin where read would do
grant("00u00000002","vault-billing-admin",300)

# ---- LEGITIMATE production access, actively used. Without this, 100% of prod
# ---- access is a finding, which looks seeded rather than discovered.
LEGIT_PROD = {"00u00000000":["db-prod-write","deploy-prod"],   # billing lead
              "00u00000004":["db-prod-write"],                  # infra
              "00u00000009":["deploy-prod"],                    # infra on-call
              "00u00000014":["deploy-prod","db-prod-write"],    # platform lead
              "00u00000023":["vault-billing-admin"]}            # billing lead
for uid, gs_ in LEGIT_PROD.items():
    for g in gs_:
        grant(uid, g, random.randint(120, 600))

# ---- THE NEW HIRE. HR provisions the identity; access is what she lacks.
# ---- STAGED, zero group memberships, and no MFA yet -- so the gate fires.
users.append({"id":"00uNEWHIRE01","status":"STAGED",
              "created":iso(NOW - dt.timedelta(days=2)),
              "profile":{"firstName":"Nadia","lastName":"Rahimi",
                         "email":"nadia.rahimi@cal.example.com",
                         "login":"nadia.rahimi@cal.example.com",
                         "title":"Software Engineer","department":"billing",
                         "startDate":"2026-09-14","manager":"sarah.chen@cal.example.com"},
              "_factors":[]})

# ---- usage logs: routine groups used recently, planted ones never
def log(uid, gid, when, ev="group.privilege.used"):
    logs.append({"uuid": f"ev{len(logs):09d}", "published": iso(when),
                 "eventType": ev, "actor": {"id": uid, "type": "User"},
                 "target": [{"id": gid, "type": "UserGroup"}]})

for m in memberships:
    gname = next(k for k,v in GID.items() if v == m["groupId"])
    uid = m["userId"]
    dormant = (uid in STALE_PROD and gname=="db-prod-write") \
              or (uid in MOVED and gname==MOVED.get(uid)) \
              or (uid=="00usvc00001") \
              or (uid=="00u00000002" and gname=="vault-billing-admin")
    if dormant:
        continue                                  # never used -> agent should find it
    # Not every grant gets exercised. Tools handed out by default (Figma, the
    # analytics warehouse, prod read) are the ones people never actually open --
    # this is the ordinary, unglamorous half of over-provisioning.
    rarely = {"figma-viewer": .80, "analytics-dashboard": .75,
              "db-prod-read": .65, "datadog-eng": .45, "jira-eng": .15}
    if random.random() < rarely.get(gname, 0.12):
        continue
    for _ in range(random.randint(3, 25)):
        log(uid, m["groupId"], NOW - dt.timedelta(days=random.randint(0, 60),
                                                  hours=random.randint(0,23)))

OUT.write_text(json.dumps({"users":users,"groups":groups,
                           "memberships":memberships,"logs":sorted(logs,key=lambda x:x["published"]),
                           "teams":TEAMS}, indent=2))
print(f"wrote {OUT}")
print(f"  users:       {len(users)}")
print(f"  groups:      {len(groups)}")
print(f"  memberships: {len(memberships)}")
print(f"  log events:  {len(logs)}")
print(f"\n  planted findings the agent should discover:")
print(f"    - 3 users with db-prod-write, unused 210 days")
print(f"    - 2 users kept old team group after moving")
print(f"    - 1 service account with infra-admin + deploy-prod, dormant 980 days")
print(f"    - 1 user with vault-billing-admin where read suffices")
print(f"    - 3 users with NO Okta Verify enrolled (grants must be blocked)")
