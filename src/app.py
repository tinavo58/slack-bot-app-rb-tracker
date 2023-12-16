#!/usr/bin/env python3
import os
import re
import asana

from pprint import pprint

from dotenv import load_dotenv; load_dotenv()
from datetime import datetime, timedelta
from asana.rest import ApiException
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError


# ------------------------------------------------------------
# slack app
app = App(
    signing_secret=os.getenv('SLACK_SIGNING_SECRET')
)


# ------------------------------------------------------------
# asana
def calculateDate(days=14):
    return datetime.strftime(datetime.now() - timedelta(days=days), '%Y-%m-%d')


def retrieveTasks(tasks_api_instance, opt_fields=None):
    opts = {
        'project': os.getenv('RB_TRACKER_P'),
        'completed_since': calculateDate(),
    }

    if opt_fields is not None:
        opts.update(opt_fields)

    return tasks_api_instance.get_tasks(opts)


def triggerAsanaInstance():
    configuration = asana.Configuration()
    configuration.access_token = os.getenv('ASANA_PAT')
    api_client = asana.ApiClient(configuration)

    return  asana.TasksApi(api_client)


def retrieveSingeTask(tasks_api_instance, gid):
    opts = {
        'opt_fields': "name,assignee.name,due_on,custom_fields.name,custom_fields.display_value,memberships.section.name,completed_at"
    }

    return tasks_api_instance.get_task(gid, opts)


def searchTasks(searchTask: str, tasks_api_instance):
    """search task based on name input
    return list of gids if any"""
    tasks = [x for x in retrieveTasks(tasks_api_instance)]

    output = []
    for task in tasks:
        if searchTask.lower() in task['name'].lower():
            output.append(task['gid'])

    return output


def getDisplayValue(field, fieldsList):
    for each in fieldsList:
        if each['name'].lower() == field.lower():
            value = each['display_value']
            if value is None:
                return "TBC"
            return value


def convertDateTime(dateTimeString, flag=False):
    if flag:
        dateTimeDetails = datetime.strptime(dateTimeString, '%Y-%m-%d')
    else:
        dateTimeDetails = datetime.strptime(dateTimeString, "%Y-%m-%dT%H:%M:%S.%fZ")

    return dateTimeDetails.strftime("%-d/%m/%Y")


def extractInfo(item):
    # client's name
    clientName = item['name']

    # assignee
    if item['assignee'] is None:
        assignee = "TBC"
    else: assignee = item['assignee']['name']

    # status
    status = getDisplayValue('Status', item['custom_fields'])

    # due date
    if item['due_on'] is None:
        dueDate = "TBC"
    else: dueDate = convertDateTime(item['due_on'], flag=True)

    # completed date
    if item['completed_at'] is None:
        completeDate = "In progress"
    else: completeDate = convertDateTime(item['completed_at'])

    return clientName, status, assignee, dueDate, completeDate

def fullSearch(searchString: str, task_api_instance):
    res = searchTasks(searchString, task_api_instance)
    if len(res) > 0:
        return [extractInfo(retrieveSingeTask(task_api_instance, gid)) for gid in res]

    return None

def extractRequiredInfo(tasksList):
    output = {}

    for each in tasksList:
        status = each['memberships'][0]['section']['name']
        client_name, status, assignee, dueDate, _ = extractInfo(each)
        taskString = f"{client_name} - Status: {status}, Assignee: {assignee}, Due date: {dueDate}"

        if status not in output:
            output[status] = []

        output[status].append(taskString)

    return output


#TODO to be deleted
def main():
    # search = "central"
    tasks_api_instance = triggerAsanaInstance()
    # res = searchTasks(search, tasks_api_instance)
    # print(res)
    # outputs = [extractInfo(retrieveSingeTask(tasks_api_instance, x)) for x in res]
    # print(outputs)
    # task = retrieveSingeTask(triggerAsanaInstance(), 1206109491240743)
    # pprint(task)
    opts = {
        'opt_fields': "name,assignee.name,due_on,custom_fields.name,custom_fields.display_value,memberships.section.name,completed_at"
    }
    res = retrieveTasks(tasks_api_instance, opt_fields=opts)
    output = extractRequiredInfo([x for x in res])
    print(output)



# ------------------------------------------------------------
# slack
@app.message(re.compile(r'check(.*)'))
def check_RB_request(client, message):
    message_text, ts, channel_id = message['text'], message['ts'], message['channel']
    task_api_instance = triggerAsanaInstance()

    # text include search text
    if len(message_text.split()) > 1:
        search = str(message_text.split(maxsplit=1)[-1])
        tasks = fullSearch(search, task_api_instance)

        if tasks is None:
            client.chat_postMessage(
            channel=channel_id,
            thread_ts=ts,
            blocks= [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": ":face_with_monocle: Unable to find such request. Request might not have been submitted (you can you submite via this <https://form.asana.com/?k=ItwSQjHfy5lxDIcIMZFv7Q&d=149498577369773|form>) or it was completed more than 2 weeks ago."
                    }
                }
            ],
            text=":face_with_monocle: Unable to find such request. Request might not have been submitted (you can you submite via this <https://form.asana.com/?k=ItwSQjHfy5lxDIcIMZFv7Q&d=149498577369773|form>) or it was completed more than 2 weeks ago."
        )

        else:
            blocks = []

            for name, status, assignee, dueDate, completeDate in tasks:
                task = {
                    "type": "rich_text",
                    "elements": [
                        {
                            "type": "rich_text_quote",
                            "elements": [
                                {
                                    "type": "text",
                                    "text": name,
                                    "style": {
                                        "bold": True
                                    }
                                },
                                {
                                    "type": "text",
                                    "text": "\n\tStatus: " + status
                                },
                                {
                                    "type": "text",
                                    "text": "\n\tAssignee: " + assignee
                                },
                                {
                                    "type": "text",
                                    "text": "\n\tDue date: " + dueDate
                                },
                                {
                                    "type": "text",
                                    "text": "\n\tCompleted date: " + completeDate
                                }
                            ]
                        }
                    ]
                }
                blocks.append(task)

            client.chat_postMessage(
                channel=channel_id,
                thread_ts=ts,
                blocks=blocks,
                text="listing results"
            )

    # if only "check" sent
    else:
        client.chat_postMessage(
            thread_ts=ts,
            channel=channel_id,
            blocks= [
                {
                    "type": "rich_text",
                    "elements": [
                        {
                            "type": "rich_text_quote",
                            "elements": [
                                {
                                    "type": "text",
                                    "text": "Please include client name e.g. "
                                },
                                {
                                    "type": "text",
                                    "text": "check client_name",
                                    "style": {
                                        "italic": True,
                                        "bold": True
                                    }
                                }
                            ]
                        }
                    ]
                }
            ],
            text="Please include client name e.g. check client_name"
        )


if __name__ == '__main__':
    # main()
    SocketModeHandler(
        app,
        os.environ['SLACK_APP_TOKEN'],
    ).start()
