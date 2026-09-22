from roboflow import Roboflow

api_key   = "f2JiQ0Vkd0JRIDZ8UP5a"
workspace = "iman-irhash"
project   = "sbs-transit-lrt"
version   = 8

rf    = Roboflow(api_key=api_key)
ws    = rf.workspace(workspace)
proj  = ws.project(project)
model = proj.version(version).model
print("SUCCESS — model loaded:", model)
