"""

  esky.fstransact:  best-effort support for transactional filesystem operations

This module provides a uniform interface to various platform-specific 
mechanisms for doing transactional filesystem operations.  On platforms where
transactions are not supported, it falls back to doing things one operation
at a time.

Currently supported platforms are:

    * Windows Vista and later, using MoveFileTransacted and friends

"""

import sys
import shutil
import os

CreateTransaction = None
if sys.platform == "win32":
    try:
        import ctypes
    except ImportError:
        pass
    else:
        try:
            ktmw32 = ctypes.windll.ktmw32
            CreateTransaction = ktmw32.CreateTransaction
            CommitTransaction = ktmw32.CommitTransaction
            RollbackTransaction = ktmw32.RollbackTransaction
            kernel32 = ctypes.windll.kernel32
            MoveFileTransacted = kernel32.MoveFileTransactedA
            CopyFileTransacted = kernel32.CopyFileTransactedA
            DeleteFileTransacted = kernel32.DeleteFileTransactedA
            RemoveDirectoryTransacted = kernel32.RemoveDirectoryTransactedA
        except (WindowsError,AttributeError):
            CreateTransaction = None


def files_differ(file1,file2):
    """Check whether two files are actually different."""
    try:
        stat1 = os.stat(file1)
        stat2 = os.stat(file2)
    except EnvironmentError:
         return True
    if stat1.st_size != stat2.st_size:
        return True
    f1 = open(file1,"rb")
    try:
        f2 = open(file2,"rb")
        try:
            data1 = f1.read(1024*256)
            data2 = f2.read(1024*256)
            while data1 and data2:
                if data1 != data2:
                    return True
                data1 = f1.read(1024*256)
                data2 = f2.read(1024*256)
            return (data1 != data2)
        finally:
            f2.close()
    finally:
        f1.close()


if CreateTransaction:

    class FSTransaction(object):
        """Utility class for transactionally operating on the filesystem.

        This particular implementation uses the transaction services provided
        by Windows Vista and later in ktmw32.dll.
        """

        def __init__(self):
            self.trnid = CreateTransaction(None,0,0,0,0,None,"")

        def move(self,source,target):
            if not files_differ(source,target):
                self.remove(source)
            srcenc = source.encode(sys.getfilesystemencoding())
            tgtenc = source.encode(sys.getfilesystemencoding())
            if os.path.exists(target):
                MoveFileTransacted(tgtenc,tgtenc+".old",None,None,1,self.trnid)
                MoveFileTransacted(srcenc,tgtenc,None,None,1,self.trnid)
                try:
                    DeleteFileTransacted(tgtenc+".old",self.trnid)
                except EnvironmentError:
                    pass
            else:
                MoveFileTransacted(srcenc,tgtenc,None,None,1,self.trnid)

        def copy(self,source,target):
            if not files_differ(source,target):
                return
            srcenc = source.encode(sys.getfilesystemencoding())
            tgtenc = source.encode(sys.getfilesystemencoding())
            if os.path.exists(target):
                MoveFileTransacted(tgtenc,tgtenc+".old",None,None,1,self.trnid)
                CopyFileTransacted(srcenc,tgtenc,None,None,None,0,self.trnid)
                try:
                    DeleteFileTransacted(tgtenc+".old",self.trnid)
                except EnvironmentError:
                    pass
            else:
                CopyFileTransacted(srcenc,tgtenc,None,None,None,0,self.trnid)

        def remove(self,target):
            tgtenc = source.encode(sys.getfilesystemencoding())
            if os.path.isdir(target):
                RemoveDirectoryTransacted(tgtenc,self.trnid)
            else:
                DeleteFileTransacted(tgtenc,self.trnid)

        def commit(self):
            CommitTransaction(self.trnid)

        def abort(self):
            RollbackTransaction(self.trnid)

else:

    class FSTransaction(object):
        """Utility class for transactionally operating on the filesystem.

        This particular implementation if the fallback for systems that don't
        support transaction filesystem operations.
        """

        def __init__(self):
            self.pending = []

        def move(self,source,target):
            if files_differ(source,target):
                self.pending.append(("_move",source,target))
            else:
                self.remove(source)

        def _move(self,source,target):
            if sys.platform == "win32" and os.path.exists(target):
                os.rename(target,target+".old")
                try:
                    os.rename(source,target)
                except:
                    os.rename(target+".old",target)
                    raise
                else:
                    try:
                        os.unlink(target+".old")
                    except EnvironmentError:
                        pass
            else:
                os.rename(source,target)

        def copy(self,source,target):
            if files_differ(source,target):
                self.pending.append(("_copy",source,target))

        def _copy(self,source,target):
            if sys.platform == "win32" and os.path.exists(target):
                os.rename(target,target+".old")
                try:
                    shutil.copy2(source,target)
                except:
                    os.rename(target+".old",target)
                    raise
                else:
                    try:
                        os.unlink(target+".old")
                    except EnvironmentError:
                        pass
            else:
                shutil.copy2(source,target)

        def remove(self,target):
            self.pending.append(("_remove",target))

        def _remove(self,target):
            if os.path.isfile(target):
                os.unlink(target)
            else:
                os.rmdir(target)

        def commit(self):
            for op in self.pending:
                getattr(self,op[0])(*op[1:])

        def abort(self):
            del self.pending[:]

