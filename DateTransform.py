# -*- coding: utf-8 -*-
"""
Created on Fri Dec 4 15:03:00 2017

@author: haoc_dp
"""

import datetime
import re


class DateTransform(object):

    def __init__(self):
        pass

    @staticmethod
    def number2date(year, number):
        fir_day = datetime.datetime(year, 1, 1)
        zone = datetime.timedelta(days=number - 1)
        return datetime.datetime.strftime(fir_day + zone, "%Y-%m-%d")

    @staticmethod
    def date2number(date):
        d = re.split('/', date)
        year = int(d[0])
        month = int(d[1])
        day = int(d[2])

        months = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
        if 0 < month <= 12:
            sum = months[month - 1]
        else:
            print
            'data error'
        sum += day
        leap = 0
        if (year % 400 == 0) or ((year % 4 == 0) and (year % 100 != 0)):
            leap = 1
        if (leap == 1) and (month > 2):
            sum += 1
        return sum
