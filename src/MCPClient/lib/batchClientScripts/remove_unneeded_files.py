print "Hello world!  I got reloaded!"

def call(jobs):
    jobs[0].set_status(0)
    jobs[0].write_output("hooray!")
