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


def searchTasks(searchTask: str, tasks_api_instance):
    """search task based on name input
    return list of gids if any"""
    tasks = retrieveTasks(tasks_api_instance, flag=True)

    output = []
    for task in tasks:
        if searchTask.lower() in task['name'].lower():
            output.append(extractInfo(task))

    return output


def getDisplayValue(field, fieldsList):
    for each in fieldsList:
        if each['name'].lower() == field.lower():
            value = each['display_value']
            if value is None:
                return "N/A"
            return value


def convertDateTime(dateTimeString, flag=False):
    """convert datetime string to usual format dd/mm/yyyy"""
    if flag:
        dateTimeDetails = datetime.strptime(dateTimeString, '%Y-%m-%d')
    else:
        dateTimeDetails = datetime.strptime(dateTimeString, "%Y-%m-%dT%H:%M:%S.%fZ")

    return dateTimeDetails.strftime("%-d/%m/%Y")


def extractInfo(item):
    """return `tuple` of required info

    Args:
        item: task returned from Asana"""

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


def fullSearch(searchString: str):
    res = searchTasks(searchString, triggerAsanaInstance())
    if len(res) > 0:
        return res

    return None


def extractRequiredInfo(tasksList) -> dict:
    output = {}

    for each in tasksList:
        section = each['memberships'][0]['section']['name']

        # check if `section` already existed in dict
        if section not in output:
            output[section] = []

        output[section].append(extractInfo(each))

    return output


def getTaskForAppHome() -> dict:
    res = retrieveTasks(triggerAsanaInstance(), flag=True)

    return extractRequiredInfo(res)


# ------------------------------------------------------------
# slack
@app.message(re.compile(r'check(.*)'))
def check_RB_request(client, message, logger):
    message_text, ts, channel_id = message['text'], message['ts'], message['channel']

    # text include search text
    if len(message_text.split()) > 1:
        search = str(message_text.split(maxsplit=1)[-1])
        tasks = fullSearch(search)

        if tasks is None:
            try:
                client.chat_postMessage(
                channel=channel_id,
                thread_ts=ts,
                attachments= [
                   {
                        "color": "#b892fe",
                        "blocks": [
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": ":face_with_monocle: Unable to find such request. Request might not have been submitted or maybe it was completed more than 2 weeks ago.",
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
                                        "action_id": "/Xhsi",
                                        "url": "https://form.asana.com/?k=ItwSQjHfy5lxDIcIMZFv7Q&d=149498577369773t"
                                    }
                                ]
                            }
                        ],
                        "fallback": "Unable to find such request. Request might not have been submitted or maybe it was completed more than 2 weeks ago."
                    }
                ]
            )

            except SlackApiError as e:
                logger.error(f"failed to post message: {e}")

        else:
            attachments = []

            for name, status, assignee, dueDate, completeDate in tasks:
                if completeDate is None:
                    task = {
                        "color": "#b892fe",
                        "blocks": [
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": "*" + name + "*" + "\n\tStatus: *" + status + "*\n\tAssignee: *" + assignee + "*\n\tDue date: *" + dueDate + "*"
                                }
                            }
                        ],
                        "fallback": name + ", Status: " + status + ", Assignee: " + assignee + ", Due Date: " + dueDate
                    }

                else:
                    task = {
                        "color": "#b892fe",
                        "blocks": [
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": "*" + name + "*" + "\n\tStatus: *" + status + "*\n\tAssignee: *" + assignee + "*\n\tCompleted date: *" + completeDate + "*"
                                }
                            }
                        ],
                        "fallback": name + ", Status: " + status + ", Assignee: " + assignee + ", Completed Date: " + completeDate
                    }

                attachments.append(task)

            try:
                client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=ts,
                    attachments=attachments,
                )

            except SlackApiError as e:
                logger.error(f"failed to post message: {e}")

    # if only "check" sent
    else:
        try:
            client.chat_postMessage(
                thread_ts=ts,
                channel=channel_id,
                attachments= [
                    {
                        "color": "#b892fe",
                        "blocks": [
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": "Please include client name e.g. check *_client_name_*"
                                }
                            }
                        ],
                        "fallback": "Please include client name e.g check client_name"
                    }
                ]
            )

        except SlackApiError as e:
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
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Submit new request",
                        "emoji": True
                    },
                    "action_id": "/Xhsi",
                    "url": "https://form.asana.com/?k=ItwSQjHfy5lxDIcIMZFv7Q&d=149498577369773t"
                }
            ]
        },
        {
            "type": "divider"
        }
	]

    tasksDict = getTaskForAppHome()
    for section in tasksDict:
		# title block
        titleBlock = {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "\n:eh-p: *" + section + "*"

            }
        }
        blocks.append(titleBlock)
        blocks.append(
            {
                "type": "divider"
            }
        )

		# tasks section
        for name, status, assignee, dueDate, completeDate in tasksDict[section]:
            if completeDate is None:
                task = {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "\n>*_" + name + "_*" + " - Status: *" + status + "*\n>Assignee: *" + assignee + "*, Due date: *" + dueDate + "*"
                    }
                }

            else:
                task = {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "\n>*_" + name + "_*" + " - Status: *" + status + "*\n>Assignee: *" + assignee + "*, Completed date: *" + completeDate + "*"
                    }
                }

            blocks.append(task)

        blocks.append(
            {
                "type": "divider"
            }
        )

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


@app.event("message")
def handle_message_events(body, logger):
    logger.info(body)


# ------------------------------------------------------------
# main app
if __name__ == '__main__':
    SocketModeHandler(
        app,
        os.environ['SLACK_APP_TOKEN'],
    ).start()
