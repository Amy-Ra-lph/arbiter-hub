from datetime import datetime, timezone


class OCSFEventFormatter:
    OCSF_VERSION = "1.3.0"

    def format_security_finding(
        self, workload_id: str, finding_type: str, severity: str, detail: dict,
    ) -> dict:
        severity_map = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        return {
            "class_uid": 2001,
            "class_name": "Security Finding",
            "category_uid": 2,
            "category_name": "Findings",
            "severity_id": severity_map.get(severity, 0),
            "severity": severity,
            "activity_id": 1,
            "activity_name": "Create",
            "status_id": 1,
            "time": datetime.now(timezone.utc).isoformat(),
            "metadata": {"version": self.OCSF_VERSION, "product": {"name": "arbiter-hub"}},
            "finding_info": {
                "title": finding_type,
                "uid": workload_id,
                "desc": str(detail),
            },
            "resources": [{"uid": workload_id, "type": "workload"}],
        }

    def format_entity_management(
        self, entity_type: str, entity_id: str, action: str, detail: dict, actor: str,
    ) -> dict:
        activity_map = {"create": 1, "delete": 2, "state_transition": 3, "update": 3}
        return {
            "class_uid": 3004,
            "class_name": "Entity Management",
            "category_uid": 3,
            "category_name": "Identity & Access Management",
            "activity_id": activity_map.get(action, 0),
            "activity_name": action,
            "time": datetime.now(timezone.utc).isoformat(),
            "metadata": {"version": self.OCSF_VERSION, "product": {"name": "arbiter-hub"}},
            "entity": {"uid": entity_id, "type": entity_type},
            "actor": {"user": {"name": actor}},
            "unmapped": detail,
        }

    def format_authorization(
        self, subject: str, action: str, resource: str, allowed: bool, reason: str,
    ) -> dict:
        return {
            "class_uid": 3003,
            "class_name": "Authorization",
            "category_uid": 3,
            "category_name": "Identity & Access Management",
            "activity_id": 1 if allowed else 2,
            "activity_name": "grant" if allowed else "deny",
            "time": datetime.now(timezone.utc).isoformat(),
            "metadata": {"version": self.OCSF_VERSION, "product": {"name": "arbiter-hub"}},
            "actor": {"user": {"name": subject}},
            "dst_endpoint": {"name": resource},
            "unmapped": {"action": action, "reason": reason},
        }

    def format_api_activity(
        self, method: str, path: str, actor: str, status_code: int,
    ) -> dict:
        return {
            "class_uid": 6003,
            "class_name": "API Activity",
            "category_uid": 6,
            "category_name": "Application Activity",
            "activity_id": 1,
            "activity_name": "api_call",
            "time": datetime.now(timezone.utc).isoformat(),
            "metadata": {"version": self.OCSF_VERSION, "product": {"name": "arbiter-hub"}},
            "api": {"operation": method, "request": {"url": {"path": path}}},
            "actor": {"user": {"name": actor}},
            "http_response": {"code": status_code},
        }
