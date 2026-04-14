path = "/etc/postgresql/17/main/pg_hba.conf"
with open(path) as f:
    content = f.read()
content = content.replace(
    "local   all             postgres                                md5",
    "local   all             postgres                                trust"
)
with open(path, "w") as f:
    f.write(content)
print("Done — postgres local auth set to trust")
