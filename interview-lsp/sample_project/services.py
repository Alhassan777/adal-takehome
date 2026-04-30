from datetime import datetime
from .models import User, Task, Project
from .utils import format_date, truncate


def create_user(id: int, name: str, email: str) -> User:
    return User(id=id, name=name, email=email, created_at=datetime.now())


def create_project(id: int, name: str, owner: User) -> Project:
    return Project(id=id, name=name, owner=owner, tasks=[])


def summarize_project(project: Project) -> str:
    pending = project.pending_tasks()
    owner_name = project.owner.display_name()
    created = format_date(project.owner.created_at)

    lines = [
        f"Project: {project.name}",
        f"Owner: {owner_name} (since {created})",
        f"Tasks: {len(project.tasks)} total, {len(pending)} pending",
    ]

    for task in pending[:5]:
        desc = truncate(task.description, 50)
        assignee = task.assignee.name if task.assignee else "unassigned"
        lines.append(f"  - [{assignee}] {task.title}: {desc}")

    return "\n".join(lines)
