"""Install/remove only this project's per-user @reboot block; no sudo required."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import time

BEGIN='# BEGIN inspection-rover workbench'
END='# END inspection-rover workbench'


def cron_content(existing, command=None):
    lines=existing.splitlines(keepends=True);out=[];inside=False
    for line in lines:
        if line.strip()==BEGIN:
            if inside:raise ValueError('Invalid nested rover crontab block')
            inside=True
        elif line.strip()==END:
            if not inside:raise ValueError('Invalid rover crontab block end')
            inside=False
        elif not inside:out.append(line)
    if inside:raise ValueError('Incomplete rover crontab block; refusing to alter it')
    result=''.join(out)
    if command:
        result=result.rstrip()+'\n\n'+BEGIN+'\n'+command+'\n'+END+'\n'
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--remove',action='store_true');args=parser.parse_args()
    if os.name!='posix':raise SystemExit('Run this installer on the Ubuntu car')
    root=Path(__file__).resolve().parents[1]
    env=os.environ.copy();env['LC_ALL']='C'
    read=subprocess.run(['crontab','-l'],capture_output=True,text=True,env=env)
    if read.returncode!=0 and 'no crontab' not in read.stderr.lower():
        raise SystemExit('Cannot read current crontab; no changes made')
    private=root/'.local-access';private.mkdir(mode=0o700,exist_ok=True)
    backup=private/('crontab-before-'+str(time.time_ns())+'.txt')
    backup.write_text(read.stdout,encoding='utf-8');backup.chmod(0o600)
    command='@reboot /bin/sh '+shlex.quote(str(root/'start_at_boot.sh'))+' >> '+shlex.quote(str(root/'runtime/boot-workbench.log'))+' 2>&1'
    new=cron_content(read.stdout,None if args.remove else command)
    subprocess.run(['crontab','-'],input=new,text=True,env=env,check=True,capture_output=True)
    current=subprocess.run(['crontab','-l'],capture_output=True,text=True,env=env,check=True).stdout
    assert current==new
    print(json.dumps(dict(installed=not args.remove,own_blocks=current.count(BEGIN),
                          existing_entries_preserved=True,private_backup=str(backup))))


if __name__=='__main__':main()
