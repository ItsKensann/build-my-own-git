import argparse
import configparser
from datetime import datetime
try:
    import grp, pwd
except ModuleNotFoundError:
    pass
from fnmatch import fnmatch
import hashlib
from math import ceil
import os
import re
import sys
import zlib

# -- Repo 
class GitRepository (object):
    """A git repository that stores worktree path, gitdir path, and config"""

    worktree = None
    gitdir = None
    conf = None

    def __init__(self, path, force=False):
        self.worktree = path
        self.gitdir = os.path.join(path, ".git")

        if not (force or os.path.isdir(self.gitdir)):
            raise Exception(f"Not a Git repository {path}")
        
        # Read config file in .git/config
        self.conf = configparser.ConfigParser()
        cf = repo_file(self, "config")

        if cf and os.path.exists(cf):
            self.conf.read([cf])
        elif not force:
            raise Exception("Configuration file missing")
        
        if not force:
            version = int(self.conf.get("core", "repositoryformatversion"))
            if version != 0:
                raise Exception(f"Unsupported repositoryformatversion: {version}")

def repo_path(repo, *path):
    """"Compute path under the repo git directory"""
    # Star on *path makes the function variadic, so it can be called with multiple path components as seperate arguments
    return os.path.join(repo.gitdir, *path)

def repo_file(repo, *path, mkdir=False):
    """Find a path to a file, but makes sure that the directory for that file is built first
       Last element should be a file
    """

    if repo_dir(repo, *path[:-1], mkdir=mkdir):
        # Find a path to the file, makes sure that everything before the last element in the path (ex. HEAD) exists first
        return repo_path(repo, *path)

def repo_dir(repo, *path, mkdir=False):
    """Checks if directory exist, if mkdir is True then create the appropriate directory with os library"""
    
    path = repo_path(repo, *path)

    # if path exists (file or directory), then checks if it is a directory, if not then raise exception
    if os.path.exists(path):
        if (os.path.isdir(path)):
            return path
        else:
            raise Exception(f"Not a directory {path}")
    
    # if path doesn't exist then make the directory if mkdir is True
    if mkdir:
        os.makedirs(path)
        return path
    else:
        return None
    
def repo_default_config():
    """Config file to setup an INI-like file with a single section [core] and three fields"""
    ret = configparser.ConfigParser()

    ret.add_section("core")
    ret.set("core", "repositoryformatversion", "0")
    ret.set("core", "filemode", "false")
    ret.set("core", "bare", "false")

    return ret
    
def repo_create(path):
    """Create a new repository at path"""

    # used with git init, so .git folder does not exist yet
    repo = GitRepository(path, force=True)

    # Raise exceptoin if path is not a directory or if github directory is not empty
    if os.path.exists(repo.worktree):
        if not os.path.isdir(repo.worktree):
            raise Exception(f"{path} is not a directory!")
        if os.path.exists(repo.gitdir) and os.listdir(repo.gitdir):
            raise Exception(f"{path} is not empty!")
    else:
        os.makedirs(repo.worktree)
    
    repo_dir(repo, "branches", mkdir=True)
    repo_dir(repo, "objects", mkdir=True)
    repo_dir(repo, "refs", "tags", mkdir=True)
    repo_dir(repo, "refs", "heads", mkdir=True)

    # .git/description
    with open(repo_file(repo, "description"), "w") as f:
        f.write("Unnamed repository; edit this file 'description' to name the repository.\n")

    # .git/HEAD
    with open(repo_file(repo, "HEAD"), "w") as f:
        f.write("ref: refs/heads/master\n")

    with open(repo_file(repo, "config"), "w") as configfile:
        config = repo_default_config()
        config.write(configfile)

    return repo

def repo_find(path=".", required=True):
    """"Function to recursively find the root of the directory"""
    path = os.path.realpath(path)

    # We will know if we have reached the root directory if the path contains a .git folder
    if os.path.isdir(os.path.join(path, ".git")):
        return GitRepository(path)

    # If haven't returned, go up one level to parent
    parent = os.path.realpath(os.path.join(path, ".."))

    if parent == path:
        # if parent==path, then path is root
        if required:
            raise Exception("No git directory.")
        else:
            return None
            # return for this base case
    
    return repo_find(path, required)

# -- Object
class GitObject (object):

    def __init__(self, data=None):
        if data:
            self.deserialize(data)

    def serialize(self, repo):
        """Function must be implemented by subclasses.
        It must read the object's contents from self.data (byte string), then convert it into a meaningful representation
        Depends on each subclass
        """
        raise Exception("Unimplemented!")

    def deserialize(self, data):
        raise Exception("Unimplemented!")

    def init(self):
        pass

class GitBlob(GitObject):
    "Subclass of GitObject"
    fmt = b"blob"

    def serialize(self):
        return self.blobdata

    def deserialize(self, data):
        self.blobdata = data

def object_read(repo, sha):
    """Reads object SHA from the git repo.
       00000000  63 6f 6d 6d 69 74 20 31  30 38 36 00 74 72 65 65  |commit 1086.tree|
       Convert sha to readable byte string using zlib
       Return a GitObject whose exact type depends on the type retrieved from the sha
    """

    path = repo_file(repo, "objects", sha[0:2], sha[2:])

    if not os.path.isfile(path):
        return None
    
    # Read the binary file and convert to readable bytes
    with open (path, "rb") as f:
        raw = zlib.decompress(f.read())

        # Read object type by finding the byte representative of " "
        x = raw.find(b" ")
        fmt = raw[0:x]

        # Locate the null byte to find the size of the object
        y = raw.find(b"\x00", x)
        size = int(raw[x:y])
        if size != len(raw)-y-1:
            raise Exception(f"Malformed object {sha}: bad length")

        # Pick constructor
        match fmt:
            case b"commit" : c=GitCommit
            case b"tree" : c=GitTree
            case b"tag" : c=GitTag
            case b"blob" : c=GitBlob
            case _:
                raise Exception(f"Unknow type {fmt.decode("ascii")} for object {sha}")

        # Send raw data to the class and return appropriate object
        return c(raw[y+1:])

def object_write(obj, repo=None):
    """Takes in an object, writes it in the proper directory based on its SHA"""
    # Serialize object data
    data = obj.serialize()
    # Add header, make everything in byte format
    result = obj.fmt + b" " + str(len(data)).encode() + b"\x00" + data
    # Compute hash as hexadecimal string
    sha = hashlib.sha1(result).hexdigest()

    if repo:
        # Compute path
        path=repo_file(repo, "objects", sha[0:2], sha[2:], mkdir=True)

        if not os.path.exists(path):
            with open(path, "wb") as f:
                # Compress and write
                f.write(zlib.compress(result))

    return sha

def object_find(repo, name, fmt=None, follow=True):
    # TODO Will implement full function later, since there areother ways to refer to objects
    return name

def cat_file(repo, obj, fmt=None):
    obj = object_read(repo, object_find(repo, obj, fmt=fmt))
    sys.stdout.buffer.write(obj.serialize())

def hash_object(fd, fmt, repo=None):
    """Hash object, writing it to .git/objects if provided"""
    data = fd.read()

    # Choose constructor according to fmt argument
    match fmt:
        case b"commit" : obj=GitCommit(data)
        case b"tree" : obj=GitTree(data)
        case b"tag" : obj=GitTag(data)
        case b"blob" : obj=GitBlob(data)

    return object_write(obj, repo)

# -- 

# Bridge functions
def cmd_init(args):
    repo_create(args.path)

def cmd_cat_file(args):
    repo = repo_find()
    cat_file(repo, args.object, fmt=args.type.encode())

def cmd_hash_object(args):
    if args.write:
        repo = repo_find() # Look for git repo if -w command provided
    else:
        repo = None

    # open contents of file and hash object
    with open(args.path, "rb") as fd:
        sha = hash_object(fd, args.type.encode(), repo)
        print(sha)

def main(argv=sys.argv[1:]):
    argparser = argparse.ArgumentParser(description="Program")
    # Initialize subparsers, which are the subcommands
    argsubparsers = argparser.add_subparsers(title="Commands", dest="command") # Tells python to save the word after the program name
    argsubparsers.required = True # Ensures user must provid a command

    # -- Add the inidividual subcommands
    # Git init
    argsp = argsubparsers.add_parser("init", help="Initialize a new, empty repository")
    argsp.add_argument("path", metavar="directory", nargs="?", default=".", help="Where to create the repository.")

    # cat-file
    argsp = argsubparsers.add_parser("cat-file", help="Provide content of repository objects")
    argsp.add_argument("type", metavar="type", choices=["blob", "commit", "tag", "tree"], help="Specify the type")
    argsp.add_argument("object", metavar="object", help="The object to display")

    # hash-object
    argsp = argsubparsers.add_parser("hash-object", help="Compute object ID and optionally creates a blob from a file")
    argsp.add_argument("-t", metavar="type", dest="type", choices=["blob", "commit", "tag", "tree"], default="blob", help="Specify the type")
    argsp.add_argument("-w", dest="write", action="store_true", help="Actually write the object into the database")
    argsp.add_argument("path", help="Read object from <file>")

    args = argparser.parse_args(argv)

    match args.command:
        case "add"          : cmd_add(args)
        case "cat-file"     : cmd_cat_file(args)
        case "check-ignore" : cmd_check_ignore(args)
        case "checkout"     : cmd_checkout(args)
        case "commit"       : cmd_commit(args)
        case "hash-object"  : cmd_hash_object(args)
        case "init"         : cmd_init(args)
        case "log"          : cmd_log(args)
        case "ls-files"     : cmd_ls_files(args)
        case "ls-tree"      : cmd_ls_tree(args)
        case "rev-parse"    : cmd_rev_parse(args)
        case "rm"           : cmd_rm(args)
        case "show-ref"     : cmd_show_ref(args)
        case "status"       : cmd_status(args)
        case "tag"          : cmd_tag(args)
        case _              : print("Bad command.")