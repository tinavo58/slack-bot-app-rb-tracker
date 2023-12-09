#!/usr/bin/env python3
import os
from pprint import pprint

from dotenv import load_dotenv; load_dotenv()
from datetime import datetime, timedelta
from asana import Client


# ------------------------------------------------------------
PAT = os.getenv('ASANA_PAT')
PROJECT = os.getenv('RB_TRACKER_P')


# ------------------------------------------------------------
def getTasks(client, params):
    return client.tasks.get_tasks(
        params=params
    )


def searchTask(task: str):
    tasksList = [x for x in retrieveTasks()]
    output = []
    for each in tasksList:
        if task.lower() in each.get('name').lower():
            output.append(each)

    return output


def retrieveTasks():
    params = {"project": PROJECT}
    params['completed_since'] = datetime.strftime(datetime.now() - timedelta(days=14), '%Y-%m-%d')
    params['opt_fields'] = {
        'name',
        'assignee.name',
        'custom_fields.name',
        'custom_fields.display_value',
        'memberships.section.name',
        'completed_at'
    }
    client = Client.access_token(PAT)

    return getTasks(client, params)


def getDisplayValue(field, fieldsList):
    for each in fieldsList:
        if each['name'].lower() == field.lower():
            return each['display_value']

    return "N/A"


def convertDateTime(dateTimeString):
    dateTimeDetails = datetime.strptime(dateTimeString, "%Y-%m-%dT%H:%M:%S.%fZ")

    return dateTimeDetails.strftime("%-d/%m/%Y")


def extractInfo(tasksList):
    output = {}

    for each in tasksList:
        status = each['memberships'][0]['section']['name']
        task = {}
        task['client'] = each['name']
        task['assignee'] = each['assignee']['name']
        task['status'] = getDisplayValue('Status', each['custom_fields'])
        task['expected_due_date'] = getDisplayValue('Expected due date', each['custom_fields'])

        taskString = f"{task['client']} - Status: {task['status']}, Assignee: {task['assignee']}, Due date: {convertDateTime(task['expected_due_date'])}"

        if status not in output:
            output[status] = []

        output[status].append(taskString)

    return output


def main():
    search = input('Search > ')
    searchList = searchTask(search)

    if len(searchList) > 0:
        pprint(extractInfo(searchList))
    else: print("No such request...")


if __name__ == '__main__':
    main()
