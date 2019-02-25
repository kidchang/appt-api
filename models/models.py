from datetime import datetime
from flask_mongoengine import MongoEngine

db = MongoEngine()

class Appointment(db.Document):
    appt_time = db.DateTimeField(requird=True, unique=True)

    def save(self, *args, **kwargs):
        return super(Appointment, self).save(*args, **kwargs)

    def __unicode__(self):
        return self.start_time.strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self):
        appt_dict = {}
        appt_dict['appt_time'] = self.appt_time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        return appt_dict
