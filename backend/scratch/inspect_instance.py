import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from sqlmodel import Session, select
from app.core.database import engine
from app.modules.workflow.model.workflow import WorkflowInstance, WorkflowExecutionLog

with Session(engine) as session:
    stmt = select(WorkflowInstance).where(WorkflowInstance.id == 10)
    inst = session.exec(stmt).first()
    if inst:
        print("Instance ID:", inst.id)
        print("Status:", inst.status)
        print("Thread ID:", inst.thread_id)
        print("Current Node:", inst.current_node)
        print("Celery Task ID:", getattr(inst, "celery_task_id", "Not Exist"))
        print("State Data:", inst.state_data)
        print("Error:", inst.error_message)
        
        # 查步骤日志
        log_stmt = select(WorkflowExecutionLog).where(WorkflowExecutionLog.instance_id == 10)
        logs = session.exec(log_stmt).all()
        print("Logs Count:", len(logs))
        for log in logs:
            print(f"Node: {log.node_name} ({log.node_id})")
            if log.node_type == "end":
                print("RAW Output Data (repr):")
                print(repr(log.output_data))
                print("---")
                # 尝试解析
                try:
                    data_dict = json.loads(log.output_data)
                    print("Workflow Output keys:", data_dict.get("workflow_output")[:50] if isinstance(data_dict.get("workflow_output"), str) else type(data_dict.get("workflow_output")))
                except Exception as e:
                    print("Parse error:", e)
    else:
        print("Not Found")
