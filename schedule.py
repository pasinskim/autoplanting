import sys
import os

from croniter import croniter
from datetime import datetime

def readCron(cronFile):
    # we can skip time zones for now
    base = datetime.now()
    entries = []
    with open(cronFile) as f:
         for line in f:
            print("line content: {}".format(line.rstrip()))
            # skip comments
            if line.startswith('#'):
                continue

            # split the line so that we have a command 
            # and the actual schedule separated
            #
            # IMPORTANT: we support cron entries 
            # without seconds field only with additional
            # one or more command fields
            try:
                data = line.rstrip().split(' ')
                if len(data) < 6:
                    raise Exception('invalid lenght of cron entry')
                sched = ' '.join(data[:5])
                cmd = data[5:]
            except Exception as e:
                print("[{}]: invalid entry: {}".format(line.rstrip(), e))
                continue

            # check if the entry is valid
            if croniter.is_valid(sched):
                print("have valid cron entry [{}]".format(sched))
                # next will return the next entry  
                # that we will need to fire as the datetime object
                next = croniter(sched, base).get_next(datetime)
                entries.append((next, cmd[0], cmd[1:]))
    return entries

def getNextJobs(cronFile):
    data = readCron(cronFile)
    data.sort()

    # if we have multiple jobs scheduled to 
    # happen the same time we should return all 
    jobs = [data[0]]
    for job in data[1:]:
        if job[0] == jobs[0][0]:
            jobs.append(job)
        else:
            break
    return jobs

# for testing
if __name__ == '__main__':
   data = readCron(sys.argv[1])
   data.sort()
   print(data)