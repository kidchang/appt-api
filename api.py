import mongoengine
import pika
import simplejson as json
import smtplib
import time

from datetime import datetime
from datetime import timedelta
from flask import current_app as app
from flask import Blueprint, request, render_template
from mongoengine.queryset.visitor import Q

import utils
from models import models

api = Blueprint('api', __name__, template_folder='templates')

APPT_SLOTS = [8, 10, 12, 14, 16, 18]
def _get_request_args(**kwargs):
    args = dict(request.args)
    for key, value in args.items():
        converter = kwargs[key]
        if isinstance(value, list):
            args[key] = [converter(item) for item in value]
        else:
            args[key] = converter(value)
    return args


@api.route('/api/appts', methods=['GET'])
def list_appts():
    appts = models.Appointment.objects
    appts = [d.to_dict() for d in appts]
    return utils.make_json_response(200, appts)


@api.route('/api/appts/<string:appt_id>', methods=['GET'])
def get_appt_info(appt_id):
    appt, error = _get_appt_by_id(appt_id)
    if error:
        return utils.make_json_response(**error)
    return utils.make_json_response(200, appt.to_dict())


@api.route('/api/appts', methods=['POST'])
def schedule_appt():
    data = utils.get_request_data()
    try:
        start_time = data['start_time']
        date = data['date']
    except KeyError:
        return utils.make_json_response(
            400,
            "Sorry I cannot schedule appointment:"
            " You did not specify a date and a time."
        )
    if not _validate_date(date):
        return utils.make_json_response(
            400,
            "Sorry we are closed on weekends."
            " Appointments can only be scheduled from Monday to Friday."
        )
    if not _validate_start_time(start_time):
        appt_slots = list(map(lambda x: str(x-12) + "PM"
            if x > 12 else str(x) + "AM"
            if x < 12 else str(x) + "PM", APPT_SLOTS))
        return utils.make_json_response(
            400,
            "Appointments can only be scheduled at " + " ".join(
                map(lambda x: "%s, " % x, appt_slots)
            )
        )
    appt = models.Appointment()
    try:
        appt_time = datetime.strptime(
            date + ' ' + start_time, '%b %d %Y %I:%M%p'
        )
    except ValueError:
        return utils.make_json_response(
            400, "You need to provide a valid time."
        )
    appt.appt_time = appt_time
    print(appt_time)
    try:
        appt.save()
    except mongoengine.errors.NotUniqueError as e:
        return utils.make_json_response(
            409,
            _unavailable_message(appt_time)
        )
    return utils.make_json_response(
        200,
        "Your appointment is scheduled on %s, at %s" % (date, start_time)
    )


@api.route('/api/appts', methods=['DELETE'])
def cancel_appt_by_time():
    data = utils.get_request_data()
    try:
        date = data['date']
        start_time = data['start_time']
    except KeyError:
        return utils.make_json_response(
            400,
            "Sorry I cannot cancel your appointment "
            "without a date and a start time."
        )
    appt_time = datetime.strptime(date + ' ' + start_time, '%b %d %Y %I:%M%p')
    appt, error = _get_appt_by_appt_time(appt_time)
    if error:
        return utils.make_json_response(
            404,
            "I am not able to find your appointment on %s, at %s" %
            (date, start_time)
        )
    appt.delete()
    return utils.make_json_response(
        200,
        "Your appointment has been successfully canceled."
    )

@api.route('/api/send_email', methods=['GET'])
def send_email():
    email_user = 'edge.lambda@gmail.com'
    email_pass = 'edge1lambda2'

    sent_from = email_user
    to = 'weidongshao@gmail.com'
    subject = 'Network Status'
    body = 'http://13.52.107.109:9999/api/network_stats'
    message = "From: " + sent_from + "\n" + "To: " + to + "\n" + "Subject:" + subject + "\n\n" + body
    server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
    server.ehlo()
    server.login(email_user, email_pass)
    server.sendmail(sent_from, to, message)
    server.close()
    return utils.make_json_response(200, 'email_sent')


@api.route("/api/network_stats")
def index():
    message = "Network Status:"
    return render_template('index.html', message=message)

def _get_appt_by_id(appt_id):
    try:
        appt = models.Appointment.objects.get(id=appt_id)
    except mongoengine.errors.ValidationError as e:
        return None, {'code': 400, 'msg': e.__str__()}
    except models.Appointment.DoesNotExist as e:
        return None, {'code': 404, 'msg': e.__str__()}
    return appt, None


def _get_appt_by_appt_time(appt_time):
    try:
        appt = models.Appointment.objects.get(appt_time=appt_time)
    except mongoengine.errors.ValidationError:
        return None, {'code': 400, 'msg': 'Invalid start time'}
    except models.Appointment.DoesNotExist:
        return None, {
            'code': 404,
            'msg': 'The appointment you are trying to cancel does not exist.'
            }
    return appt, None

def _validate_date(date):
    date_obj = datetime.strptime(date, "%b %d %Y")
    return date_obj.weekday() not in [6, 7]

def _validate_start_time(start_time):
    try:
        stripped_time = int(start_time.split(':')[0])
    except ValueError:
        return False
    if start_time.endswith('PM') and not start_time.startswith('12'):
        stripped_time += 12
    return stripped_time in APPT_SLOTS

def _get_available_appts(date):
    next_day = date + timedelta(days=1)
    appts = models.Appointment.objects(
        Q(appt_time__gte=date) & Q(appt_time__lte=next_day)
    ).all()
    hours = [a.appt_time.hour for a in appts]
    time_list = list(set(APPT_SLOTS) - set(hours))
    return list(map(lambda x: str(x-12) + "PM"
        if x > 12 else str(x) + "AM" if x < 12 else str(x) + "PM", time_list))

def _unavailable_message(appt_time):
    available_appts = _get_available_appts(appt_time.date())
    hour = str(appt_time.hour - 12) + "PM" \
        if appt_time.hour > 12 else str(appt_time.hour) + "AM" \
        if appt_time.hour < 12 else str(appt_time.hour) + "PM"
    return str(hour) + " is already taken, you may select " + " ".join(
        map(lambda x: "%s, " % x, available_appts)) + "on the same day."
