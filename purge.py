import os

DIRS = ["csv", "logs", "email"]

for d in DIRS:
    if not os.path.isdir(d):
        print("skip (no dir):", d)
        continue

    for name in os.listdir(d):
        path = os.path.join(d, name)

        if os.path.isfile(path):
            try:
                os.remove(path)
                print("deleted:", path)
            except Exception as e:
                print("error:", path, e)

print("done.")
