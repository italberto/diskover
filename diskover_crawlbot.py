#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""diskover - Elasticsearch file system crawler
diskover is a file system crawler that index's
your file metadata into Elasticsearch.
See README.md or https://github.com/shirosaidev/diskover
for more information.

Copyright (C) Chris Park 2017
diskover is released under the Apache 2.0 license. See
LICENSE for the full license text.
"""

import diskover
from random import randint
import time
import sys
import os
import threading


global dirlist


def bot_thread(threadnum, cliargs, logger, rootdir_path, reindex_dict):
    """This is the bot thread function.
    It grabs a directory and it's mtime from the Queue.
    Directory mtime on disk is checked and if newer it is
    reindexed (non-recursive).
    """

    starttime = time.time()
    t = time.time()
    c = 0
    n = 0
    s = 0
    last_path = ''
    while True:
        if time.time() - t >= 60:
            t = diskover.get_time(time.time() - starttime)
            # display stats if 1 min elapsed
            logger.info(
                '### crawlbot thread-%s: %s dirs checked (%s dir/s), %s dirs updated, %s same dir hits, running for %s ###',
                threadnum, n, round(n / (time.time() - starttime), 2), c, s, t)
            t = time.time()
        # break if dirlist is None
        if dirlist is None:
            break
        else:
            # random pick from dirlist
            i = len(dirlist) - 1
            li = randint(0, i)
            path = dirlist[li][1]
            mtime_utc = dirlist[li][2]
        # pick a new path if same as last time
        if path == last_path:
            s += 1
            continue
        last_path = path
        # check directory's mtime on disk
        try:
            mtime_now_utc = time.mktime(time.gmtime(os.lstat(path).st_mtime))
        except (IOError, OSError):
            if cliargs['verbose']:
                logger.info('Error crawling directory %s' % path)
            continue
        if (mtime_now_utc == mtime_utc):
            if cliargs['verbose']:
                logger.info('Mtime unchanged: %s' % path)
        else:
            c += 1
            logger.info('*** Mtime changed! Reindexing: %s' % path)
            # delete existing path docs (non-recursive)
            reindex_dict = diskover.index_delete_path(path, cliargs, logger, reindex_dict)
            # start crawling
            diskover.crawl_tree(path, cliargs, logger, reindex_dict)
            # calculate directory size for path
            diskover.calc_dir_sizes(cliargs, logger, path=path)
        time.sleep(diskover.config['botsleep'])
        n += 1


def start_crawlbot_scanner(cliargs, logger, rootdir_path, botdirlist, reindex_dict):
    """This is the start crawl bot continuous scanner function.
    It gets a list with all the directory docs from index_get_docs which
    contains paths and their mtimes. The list is randomly shuffled.
    """
    global dirlist

    logger.info('diskover crawl bot continuous scanner starting up')
    logger.info('Randomly scanning for changes every %s sec using %s threads',
                diskover.config['botsleep'], diskover.config['botthreads'])
    logger.info('*** Press Ctrl-c to shutdown ***')

    dirlist = botdirlist

    threadlist = []
    try:
        for i in range(diskover.config['botthreads']):
            thread = threading.Thread(target=bot_thread,
                                      args=(i, cliargs, logger, rootdir_path, reindex_dict,))
            thread.daemon = True
            threadlist.append(thread)
            thread.start()

        starttime = time.time()
        # start infinite loop and randomly pick directories from dirlist
        # in future will create better algorithm for this
        while True:
            # every 1 hour get a new dirlist to pick up any new directories which have been added
            # every 1 hour update disk space info in es index
            # every 1 hour calculate directory sizes
            time.sleep(3600)
            t = time.time()
            elapsed = diskover.get_time(t - starttime)
            logger.info(
                '*** crawlbot: getting new dirlist from ES, crawlbot has been running for %s', elapsed)
            dirlist = diskover.index_get_docs(cliargs, logger, doctype='directory')
            # add disk space info to es index
            diskover.add_diskspace(cliargs['index'], rootdir_path)
            # calculate directory sizes and items
            diskover.calc_dir_sizes(cliargs, logger)

    except KeyboardInterrupt:
        print('Ctrl-c keyboard interrupt, shutting down...')
        dirlist = None
        sys.exit(0)
