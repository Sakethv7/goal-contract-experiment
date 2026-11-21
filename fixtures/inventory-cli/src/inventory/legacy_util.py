import os, sys
import json


def formatMoney( value ):
    return "$%.2f" %  value   


def  roundUp(x):
    return int(x)+1 if x!=int(x) else int(x)
