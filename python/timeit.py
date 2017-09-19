import datetime

def timeit(func, *args, **kwargs):
    """Boiler plate decorator for timing functions"""
    def wrapper(*args, **kwargs):
        t0 = datetime.datetime.utcnow()
        print "Calling: {func}".format(func=func.__name__)
        result = func(*args, **kwargs)
        delta = datetime.datetime.utcnow() - t0
        print "Elapsed time for {func} in seconds: {delta}".format(delta=delta.total_seconds(), func=func.__name__)
        return result
    return wrapper

