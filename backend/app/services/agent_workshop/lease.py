"""A process-wide OS lease, released automatically on controller death."""
import os


class CampaignLease:
    @staticmethod
    def is_held(directory):
        """Probe an existing OS lock without creating or changing campaign data."""
        try:
            file = (directory / 'run.lock').open('r+b')
        except FileNotFoundError:
            return False
        except OSError:
            return None
        with file:
            try:
                file.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
                    msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(file.fileno(), fcntl.LOCK_UN)
            except OSError:
                return True
        return False

    def __init__(self, directory):
        self.file = (directory / 'run.lock').open('a+b')
        if self.file.tell()==0:
            self.file.write(b'0'); self.file.flush()
        self.file.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise ValueError('Cette campagne est déjà pilotée par un autre processus.') from exc

    def close(self):
        if not self.file.closed:
            self.file.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_UN)
            self.file.close()
