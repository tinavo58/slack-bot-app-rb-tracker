#!/usr/bin/env python3
import os
import re
import asana

from dotenv import load_dotenv; load_dotenv()
from datetime import datetime, timedelta
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


def triggerAsanaInstance():
    configuration = asana.Configuration()
    configuration.access_token = os.getenv('ASANA_PAT')
    api_client = asana.ApiClient(configuration)

    return  asana.TasksApi(api_client)


def retrieveTasks(tasks_api_instance, flag=False):
    opt_fields = {
        'opt_fields': "name,assignee.name,due_on,custom_fields.name,custom_fields.display_value,memberships.section.name,completed_at"
    }

    opts = {
        'project': os.getenv('RB_TRACKER_P'),
        'completed_since': calculateDate(),
    }

    if flag:
        opts.update(opt_fields)

    return tasks_api_instance.get_tasks(opts)


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
                return "N/A"
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
        assignee = "N/A"
    else: assignee = item['assignee']['name']

    # status
    status = getDisplayValue('Status', item['custom_fields'])

    # due date
    if item['due_on'] is None:
        dueDate = "N/A"
    else: dueDate = convertDateTime(item['due_on'], flag=True)

    # completed date
    completeDate = item['completed_at']
    if completeDate is not None: completeDate = convertDateTime(item['completed_at'])

    return clientName, status, assignee, dueDate, completeDate


def fullSearch(searchString: str, task_api_instance):
    res = searchTasks(searchString, task_api_instance)
    if len(res) > 0:
        return [extractInfo(retrieveSingeTask(task_api_instance, gid)) for gid in res]

    return None


def extractRequiredInfo(tasksList):
    output = {}

    for each in tasksList:
        section = each['memberships'][0]['section']['name']
        client_name, status, assignee, dueDate, completeDate = extractInfo(each)

        # check if `compelted` or `in progress`
        if completeDate is None:
            taskString = f"{client_name} - Status: {status}, Assignee: {assignee}, Due date: {dueDate}"
        else:
            taskString = f"{client_name} - Status: {status}, Assignee: {assignee}, Completed date: {completeDate}"

        if section not in output:
            output[section] = []

        output[section].append(taskString)

    return output

def getTaskForAppHome():
    tasks_api_instance = triggerAsanaInstance()
    res = retrieveTasks(tasks_api_instance, flag=True)
    return extractRequiredInfo([x for x in res])


# ------------------------------------------------------------
# slack
@app.message(re.compile(r'check(.*)'))
def check_RB_request(client, message, logger):
    message_text, ts, channel_id = message['text'], message['ts'], message['channel']
    task_api_instance = triggerAsanaInstance()

    # text include search text
    if len(message_text.split()) > 1:
        search = str(message_text.split(maxsplit=1)[-1])
        tasks = fullSearch(search, task_api_instance)

        if tasks is None:
            try:
                client.chat_postMessage(
                channel=channel_id,
                thread_ts=ts,
                blocks= [
                    {
                        "type": "section",
                        "text": {
                            "type": "plain_text",
                            "text": ":face_with_monocle: Unable to find such request. Request might not have been submitted or maybe it was completed more than 2 weeks ago.",
                            "emoji": True
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Submit new request",
                                    "emoji": True
                                },
                                "value": "click_me_123",
                                "action_id": "/Xhsi",
                                "url": "https://form.asana.com/?k=ItwSQjHfy5lxDIcIMZFv7Q&d=149498577369773t"
                            }
                        ]
                    }
                ],
                text=":face_with_monocle: Unable to find such request. Request might not have been submitted (you can submit RB request via this <https://form.asana.com/?k=ItwSQjHfy5lxDIcIMZFv7Q&d=149498577369773|form>) or maybe it was completed more than 2 weeks ago."
            )

            except SlackApiError as e:
                logger.error(f"failed to post message: {e}")

        else:
            blocks = []

            for name, status, assignee, dueDate, completeDate in tasks:
                if completeDate is None:
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
                                    }
                                ]
                            }
                        ]
                    }

                else:
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
                                        "text": "\n\tCompleted date: " + completeDate
                                    }
                                ]
                            }
                        ]
                    }

                blocks.append(task)

            try:
                client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=ts,
                    blocks=blocks,
                    text="listing results"
                )

            except e:
                logger.error(f"failed to post message: {e}")

    # if only "check" sent
    else:
        try:
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

        except e:
            logger.error(f"failed to post message: {e}")


@app.action("/Xhsi")
def handle_some_action(ack, body, logger):
    ack()
    logger.info(body)


def updateView():
    blocks = [
		{
			"type": "header",
			"text": {
				"type": "plain_text",
				"text": "Rule Build Requests Update",
				"emoji": True
			}
		},
		{
			"type": "divider"
		}
	]

    tasksDict = getTaskForAppHome()
    for section in tasksDict:
		# title block
        titleBlock = {
            "type": "rich_text",
            "elements": [
                {
                    "type": "rich_text_section",
                    "elements": [
                        {
                            "type": "text",
                            "text": section,
                            "style": {
                                "bold": True
                            }
                        }
                    ]
                }
            ]
        }
        blocks.append(titleBlock)

		# tasks section
        tasksBlock = {
            "type": "section",
            "text":  {
                "type": "mrkdwn",
                "text": '\n'.join(tasksDict[section])
            }
        }
        blocks.append(tasksBlock)
        blocks.append(dict(type='divider'))


    view = {
        "type": "home",
        "blocks": blocks
    }

    return view


@app.event("app_home_opened")
def update_home_tab(client, event, logger):
    try:
        client.views_publish(
            user_id=event['user'],
            view=updateView()
        )
    except SlackApiError as e:
        logger.error(f"failed to update Home tab: {e}")


# ------------------------------------------------------------
# main app
if __name__ == '__main__':
    SocketModeHandler(
        app,
        os.environ['SLACK_APP_TOKEN'],
    ).start()
