"""Strict local stdio fixture: never imports or starts Codex/a provider."""
import json, sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
def emit(value): print(json.dumps(value),flush=True)
for line in sys.stdin:
    request=json.loads(line);method=request.get("method")
    if method=="initialize":emit({"id":request["id"],"result":{}})
    elif method=="thread/start":emit({"id":request["id"],"result":{"thread":{"id":"fixture-thread"}}})
    elif method=="turn/start":
        emit({"id":request["id"],"result":{"turn":{"id":"fixture-turn"}}})
        emit({"method":"item/completed","params":{"item":{"type":"agentMessage","id":"public-1","phase":"commentary","text":"Reading the harmless local fixture."}}})
        for kind,parsed in (("commandExecution",[{"type":"read"}]),("commandExecution",[{"type":"search"}]),("fileChange",[])):
            emit({"method":"item/started","params":{"item":{"type":kind,"id":kind+str(parsed),"commandActions":parsed}}})
        emit({"method":"item/completed","params":{"item":{"type":"reasoning","id":"private","text":"HIDDEN-MUST-NOT-PROJECT"}}})
        emit({"id":90,"method":"item/commandExecution/requestApproval","params":{
            "threadId":"fixture-thread","turnId":"fixture-turn","itemId":"fixture-action","startedAtMs":1,
            "command":"fixture marker only","cwd":str(root),"reason":"Local synthetic one-shot qualification",
            "availableDecisions":["accept","decline","cancel"]}})
    elif request.get("id")==90:
        choice=request["result"].get("decision")
        emit({"method":"serverRequest/resolved","params":{"requestId":90,"threadId":"fixture-thread"}})
        if choice=="accept":
            with (root/"fixture-action-once").open("x") as stream:stream.write("synthetic-only")
            emit({"method":"item/completed","params":{"item":{"type":"commandExecution","id":"fixture-action","status":"completed"}}})
        emit({"method":"item/completed","params":{"item":{"type":"agentMessage","id":"final","phase":"final_answer","text":'{"fixture":"complete"}'}}})
        emit({"method":"turn/completed","params":{"turn":{"status":"completed"}}})
        break
