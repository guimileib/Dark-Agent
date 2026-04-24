import json
import logging
import os
import tempfile
from enum import Enum
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Dict
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


def _atomic_write_json(path: Path, data) -> None:
    """Escreve JSON de forma atômica: arquivo temporário + os.replace.

    Garante que um crash no meio do dump não corrompa o arquivo original —
    ou o conteúdo antigo continua intacto, ou o novo substitui integralmente.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

class SocialPlatform(Enum):
    YOUTUBE = "YouTube"
    INSTAGRAM = "Instagram"
    TIKTOK = "TikTok"

@dataclass
class SocialAccount:
    id: str
    platform: str
    username: str
    token: Optional[str] = None
    # For future expansion:
    refresh_token: Optional[str] = None
    expires_at: Optional[float] = None
    
    @classmethod
    def from_dict(cls, data):
        return cls(**data)
    
    def to_dict(self):
        return asdict(self)

@dataclass
class ScheduledPost:
    id: str
    video_path: str
    platform_ids: List[str] # List of account IDs
    scheduled_time: str # ISO format string
    title: str = ""
    description: str = ""
    status: str = "pending" # pending, posting, posted, failed
    error_message: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    @property
    def dt_scheduled(self) -> datetime:
        return datetime.fromisoformat(self.scheduled_time)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)
    
    def to_dict(self):
        return asdict(self)

class SocialManager:
    """Manages social accounts and scheduled posts."""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.accounts_file = data_dir / "social_accounts.json"
        self.posts_file = data_dir / "scheduled_posts.json"
        
        self.accounts: Dict[str, SocialAccount] = {}
        self.posts: List[ScheduledPost] = []
        
        self._load_data()
        
    def _load_data(self):
        # Load Accounts
        if self.accounts_file.exists():
            try:
                with open(self.accounts_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for acc_data in data:
                        acc = SocialAccount.from_dict(acc_data)
                        self.accounts[acc.id] = acc
            except Exception as e:
                logger.error(f"Error loading accounts: {e}")
                
        # Load Posts
        if self.posts_file.exists():
            try:
                with open(self.posts_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for post_data in data:
                        post = ScheduledPost.from_dict(post_data)
                        self.posts.append(post)
            except Exception as e:
                logger.error(f"Error loading posts: {e}")

    def save_data(self):
        try:
            _atomic_write_json(
                self.accounts_file,
                [a.to_dict() for a in self.accounts.values()],
            )
        except Exception as e:
            logger.error(f"Error saving accounts: {e}")

        try:
            _atomic_write_json(
                self.posts_file,
                [p.to_dict() for p in self.posts],
            )
        except Exception as e:
            logger.error(f"Error saving posts: {e}")

    def add_account(self, platform: str, username: str, token: str = None) -> SocialAccount:
        account_id = str(uuid.uuid4())
        account = SocialAccount(
            id=account_id,
            platform=platform,
            username=username,
            token=token
        )
        self.accounts[account_id] = account
        self.save_data()
        return account

    def remove_account(self, account_id: str):
        if account_id in self.accounts:
            del self.accounts[account_id]
            self.save_data()

    def schedule_post(self, video_path: str, account_ids: List[str], scheduled_time: datetime, title: str, description: str) -> ScheduledPost:
        post = ScheduledPost(
            id=str(uuid.uuid4()),
            video_path=str(video_path),
            platform_ids=account_ids,
            scheduled_time=scheduled_time.isoformat(),
            title=title,
            description=description
        )
        self.posts.append(post)
        self.save_data()
        return post

    def remove_post(self, post_id: str):
        self.posts = [p for p in self.posts if p.id != post_id]
        self.save_data()

    def get_due_posts(self) -> List[ScheduledPost]:
        now = datetime.now()
        due = []
        for post in self.posts:
            if post.status == "pending" and post.dt_scheduled <= now:
                due.append(post)
        return due

    def mark_post_status(self, post_id: str, status: str, error: str = None):
        for post in self.posts:
            if post.id == post_id:
                post.status = status
                post.error_message = error
                self.save_data()
                break
