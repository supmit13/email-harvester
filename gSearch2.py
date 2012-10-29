import os, sys, re, time, gzip
from StringIO import StringIO
import urllib, urllib2, httplib
from BeautifulSoup import BeautifulSoup
from urlparse import urlparse


url = "http://www.google.co.in/search?sourceid=chrome&ie=UTF-8&q=##PLACEHOLDER##&oq=##PLACEHOLDER##&start=##PAGENUM##"

placeholderPattern = re.compile("##PLACEHOLDER##")
pageNumPattern = re.compile("##PAGENUM##")
#emailIdPattern = re.compile(r"(\w+\.?\w{0,}@\w+\.\w+\.?\w*)", re.MULTILINE | re.DOTALL)
emailIdPattern = re.compile(r"\W(\w+\.?\w{0,}@\w+\.\w+\.?\w*)\W", re.MULTILINE | re.DOTALL)
absUrlPattern = re.compile(r"^https?:\/\/", re.IGNORECASE)
anchorTagPattern = re.compile(r"<a\s+[^>]{0,}href=([^\s\>]+)\s?.*?>\s*\w+", re.IGNORECASE | re.MULTILINE | re.DOTALL)
bookmarkLinkPattern = re.compile("^#",re.MULTILINE | re.DOTALL)
doubleQuotePattern = re.compile('"', re.MULTILINE | re.DOTALL)

httpHeaders = { 'User-Agent' : r'Mozilla/5.0 (X11; Linux i686) AppleWebKit/535.19 (KHTML, like Gecko) Chrome/18.0.1025.162 Safari/535.19',  'Accept' : 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'Accept-Language' : 'en-US,en;q=0.8', 'Accept-Encoding' : 'gzip,deflate,sdch', 'Accept-Charset' : 'ISO-8859-1,utf-8;q=0.7,*;q=0.3', 'Connection' : 'keep-alive'}

MAX_PROCESSING_TIME = 180 # Maximum time in ms that can be spent on processing a specific website


def decodeGzippedContent(encoded_content):
    response_stream = StringIO(encoded_content)
    decoded_content = ""
    try:
        gzipper = gzip.GzipFile(fileobj=response_stream)
        decoded_content = gzipper.read()
    except: # Maybe this isn't gzipped content after all....
        decoded_content = encoded_content
    return(decoded_content)


def _searchGoogle(targetString, pageNum=0):
    global httpHeaders
    blockSize = 10
    startBlock = (pageNum * blockSize).__str__()
    targetString = targetString.replace(" ", "+")
    targetUrl = re.sub(placeholderPattern, targetString, url)
    targetUrl = re.sub(pageNumPattern, startBlock, targetUrl)
    pageRequest = urllib2.Request(targetUrl, None, httpHeaders)
    try:
    	httpResponse = urllib2.urlopen(pageRequest)
	pageContent = decodeGzippedContent(httpResponse.read())
    except:
	print "Could not fetch the page: %s"%sys.exc_info()[1].__str__()
	return None
    return pageContent


def _getSearchResults(searchPageContent):
    startPhrase = "<body"
    endPhrase = "function _gjp(){"
    pageParts = searchPageContent.split(startPhrase)
    desiredPart = pageParts[1]
    pageParts2 = desiredPart.split(endPhrase)
    desiredPart = pageParts2[0]
    #return desiredPart
    h3classrPattern = re.compile("<h3\s+class=\"r\">", re.IGNORECASE | re.MULTILINE | re.DOTALL)
    # Here, find out <h3 class="r">....
    allSearchHits = h3classrPattern.split(desiredPart)
    allAnchorLinks = []
    for searchHit in allSearchHits:
	try:
	    soup = BeautifulSoup(searchHit)
	    anchor = soup.find("a")
    	    if anchor is not None and anchor.has_key("href"):
	    	href = anchor['href']
	    	allAnchorLinks.append(href)
	except:
	    continue
    return allAnchorLinks


# 'conductGoogleSearch' actually calls '_searchGoogle' and '_getSearchResults' to do the job of actually
# searching and parsing the google search pages and returns a tuple of URLs pointing to the various sites
# that appeared in the search listing. The arguments to this function are the search string and the 
# count of pages that need to be traversed.
def conductGoogleSearch(searchString, pageDepth):
    searchPage = _searchGoogle(searchString) # Get the first search page.
    pageCtr = 0
    anchors = []
    anchors = _getSearchResults(searchPage)
    while pageCtr < pageDepth:
	pageCtr += 1
	searchPage = _searchGoogle(searchString, pageCtr)
	anchors2 = []
    	anchors2 = _getSearchResults(searchPage)
	if not anchors2:
	    continue
	anchors.extend(anchors2)
    anchors = tuple(anchors)
    return anchors


def _isAbsoluteUrl(url):
    s = absUrlPattern.search(url)
    if s:
        return True
    else:
        return False


def _getDomain(webUrl):
    obj = urlparse(webUrl)
    domain = obj.netloc
    domain = re.sub(re.compile(r"\:\d{2,4}"), "", domain)
    return(domain)


# This method checks for all anchor tags only. Other tags may be handled later. Returns a list of unique URLs
def _findAllLocalPageUrls(domain, baseUrl, pageContent):
    print "Fetching all local URLs from this page.\nAssumption: We will find all relevant local URLs from this page."
    allAnchors = re.findall(anchorTagPattern, pageContent)
    urlsDict = {}
    domainPattern = re.compile(domain, re.IGNORECASE)
    for anchor in allAnchors:
	anchor = re.sub(doubleQuotePattern, "", anchor)
	if bookmarkLinkPattern.search(anchor): # We don't want bookmark links that point inside the same page.
	    continue
	if not _isAbsoluteUrl(anchor):
	    anchor = baseUrl + anchor
	    urlsDict[anchor.__str__()] = 1
	else:
	    domainSearch = domainPattern.search(anchor)
	    if domainSearch:
		urlsDict[anchor.__str__()] = 1
    return urlsDict.keys()


# This method extracts email Ids from the content of the website whose URL has been passed in as the argument
# named 'webUrl'. It returns a list of email Ids found in the page.
def extractRelevantEmails(webUrl, context=None):
    global httpHeaders
    emailIds = []
    print "Processing URL: %s"%webUrl
    domain = _getDomain(webUrl)
    obj = urlparse(webUrl)
    baseUrl = obj.scheme + "://" + domain
    emailsDict = {baseUrl : []}
    pageRequest = urllib2.Request(webUrl, None, httpHeaders) # if the page needs authentication, we can't help at this point.
    pageContent = ""
    try:
	pageResponse = urllib2.urlopen(pageRequest)
	pageContent = decodeGzippedContent(pageResponse.read())
	pageContent = pageContent.decode("ascii", "ignore")
    except:
	print "Could not fetch the page '%s': %s"%(webUrl, sys.exc_info()[1].__str__())
	return None
    allemails = re.findall(emailIdPattern, pageContent)
    for emailmatch in allemails:
	emailIds.append(emailmatch)
    allUrls = _findAllLocalPageUrls(domain, baseUrl, pageContent) # These are supposed to be unique
    pageContent = ""
    for url in allUrls:
	print "Fetching page: %s"%url
	pageRequest = urllib2.Request(url, None, httpHeaders) # if the page needs authentication, we can't help at this point.
	try:
	    pageResponse = urllib2.urlopen(pageRequest)
	    pageContent = decodeGzippedContent(pageResponse.read())
    	except:
	    print "Could not fetch the page '%s': %s"%(url, sys.exc_info()[1].__str__())
	    return None
	allemails = re.findall(emailIdPattern, pageContent)
    	for emailmatch in allemails:
	    emailIds.append(emailmatch)
    return(emailIds)


# This method checks if the list of anchors/links passed as argument has unique domains. 
# If not, we retain only the first anchor/link and drop all the subsequent anchors.
# This should be fine since when we process the first anchor, we will process all pages
# from the website. Of course, we assume, though I am not sure if we may do so, that
# the dropped link appears as a link in the page being processed.
def checkDomainUniqueness(anchorsList):
    uniqueDomainAnchorsDict = {}
    for anchor in anchorsList:
	domain = _getDomain(anchor)
	if uniqueDomainAnchorsDict.has_key(domain): # We already have a link for this domain.
	    continue
	else: 
	    uniqueDomainAnchorsDict[domain] = anchor
    return(uniqueDomainAnchorsDict.values())
	
	    
"""
The logic after doing google search would be as follows:
First, it will check to see if the URL specified by google
search contains emails or not. If there are emails, pick
them up. Next traverse the entire webiste looking for contextual
phrases in them. If there is atleast one of the contextual phrases,
try to find emails from the page and stuff them. This way we can
cover all the urls from google search.

"""
    


if __name__ == "__main__":
    targetString = sys.argv[1]
    googleNumPages = 10
    if sys.argv.__len__() > 2:
	googleNumPages = sys.argv[2]
    if sys.argv.__len__() > 3:
	outfile = sys.argv[3]
    print "Number of pages of search listings: %s"%googleNumPages
    anchorList = conductGoogleSearch(targetString, int(googleNumPages))
    # ====================================================
    # Check and retrieve unique domains only
    anchorList2 = checkDomainUniqueness(anchorList)
    fw = open("/home/supmit/work/odesk/WheelsOfItaly/uniqueDomains1.txt", "w")
    fw.write("\n".join(anchorList2))
    fw.close()
    # ====================================================
    mycontext = [re.compile(r"Ferrari\s+for\s+Sale", re.IGNORECASE), re.compile(r"Ferrari's.*?Sale", re.IGNORECASE), re.compile(r"Sale\s+.*?Ferrari", re.IGNORECASE), re.compile(r"Looking\s+.*?Ferrari", re.IGNORECASE), re.compile(r"Rent\s+.*?Ferrari", re.IGNORECASE),]
    emails = []
    for anchor in anchorList:
    	emailsList = extractRelevantEmails(anchor, mycontext)
	if not emailsList:
	    continue
	emails.extend(emailsList)
    emailsDict = {}
    for email in emails:
	if emailsDict.has_key(email):
	    continue
	else:
	    emailsDict[email] = 1
    fwem = open(outfile, "w")
    print "\n\n==============================================================================================================\n"
    print "\n".join(emailsDict.keys())
    fwem.write("\n".join(emailsDict.keys()))
    print "\n\n==============================================================================================================\n"
    fwem.close()

     
