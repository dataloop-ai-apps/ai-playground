import dtlpy as dl
import os

dl.setenv('rc')

dl.login_m2m(email=os.getenv('EMAIL'), password=os.getenv('PASSWORD'))
