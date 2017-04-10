import urllib2
import os
import time
from functools import wraps


def retry(ExceptionToCheck, tries=4, delay=3, backoff=2, logger=None):
    """Retry calling the decorated function using an exponential backoff.

    http://www.saltycrane.com/blog/2009/11/trying-out-retry-decorator-python/
    original from: http://wiki.python.org/moin/PythonDecoratorLibrary#Retry

    :param ExceptionToCheck: the exception to check. may be a tuple of
        exceptions to check
    :type ExceptionToCheck: Exception or tuple
    :param tries: number of times to try (not retry) before giving up
    :type tries: int
    :param delay: initial delay between retries in seconds
    :type delay: int
    :param backoff: backoff multiplier e.g. value of 2 will double the delay
        each retry
    :type backoff: int
    :param logger: logger to use. If None, print
    :type logger: logging.Logger instance
    """
    def deco_retry(f):

        @wraps(f)
        def f_retry(*args, **kwargs):
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return f(*args, **kwargs)
                except ExceptionToCheck, e:
                    msg = "%s, Retrying in %d seconds..." % (str(e), mdelay)
                    if logger:
                        logger.warning(msg)
                    else:
                        print msg
                    time.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            return f(*args, **kwargs)

        return f_retry  # true decorator

    return deco_retry
#decrator from http://stackoverflow.com/questions/9446387/how-to-retry-urllib2-request-when-fails
@retry(urllib2.URLError, tries=4, delay=0.1, backoff=2)
def urlopen_with_retry(url):
    return urllib2.urlopen(url)    
    
if __name__ == '__main__':
    """
    donwloading gifs and captions
    """
    if not os.path.isdir('data'):
        os.mkdir('data')
    captions_f = urlopen_with_retry("https://raw.githubusercontent.com/raingo/TGIF-Release/master/data/tgif-v1.0.tsv")
    with open('./data/gif-url-captions.tsv','wb') as f:
        f.write(captions_f.read())
    with open('./data/gif-url-captions.tsv', 'r') as f:
        caption_data = f.readlines()
    clean_captions = ''.join(['\t'.join([line.split('\t')[0].split('/')[-1],' '.join(line.split('\t')[1:])]) for line in caption_data])
    with open('./captions.txt','wb') as f:
        f.write(clean_captions)
    #let's download the gifs
    gif_urls = [line.split('\t')[0] for line in caption_data]
    for gif in gif_urls:
        try:
            gif_f = urlopen_with_retry(gif)
            with open('./gifs/'+gif.split('/')[-1],'wb') as f:
                f.write(gif_f.read())
        except:
            print "could not download%s"%(gif)
            pass
    


