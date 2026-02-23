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


def main(argv=sys.argv[1:]):
    argparser = argparse.ArgumentParser(description="Program")
    argsubparsers = argparser.add_subparsers(title="Commands", dest="command")
    argsubparsers.required = True # Ensures user must provid a command


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