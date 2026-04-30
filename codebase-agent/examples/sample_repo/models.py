from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class User:
    id: int
    name: str
    email: str
    created_at: datetime

    def display_name(self) -> str:
        return f"{self.name} <{self.email}>"


@dataclass
class Task:
    id: int
    title: str
    description: str
    assignee: Optional[User] = None
    completed: bool = False

    def assign_to(self, user: User) -> None:
        self.assignee = user

    def mark_done(self) -> None:
        self.completed = True


@dataclass
class Project:
    id: int
    name: str
    owner: User
    tasks: list[Task]

    def pending_tasks(self) -> list[Task]:
        return [t for t in self.tasks if not t.completed]

    def add_task(self, task: Task) -> None:
        self.tasks.append(task)
