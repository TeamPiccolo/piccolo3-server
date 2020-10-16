Using CoAP to talk to piccolo server
====================================
The piccolo3 server uses the [constrained application protocol](https://en.wikipedia.org/wiki/Constrained_Application_Protocol)
to expose its functionality. The [piccolo3-client](https://github.com/TeamPiccolo/piccolo3-client) package uses coap under the 
hood to communicate with the server.

Sometimes it is useful to be able to talk CoAP directly to see what is going on. You can use any CoAP client. For the examples below 
I use [libcoap](https://libcoap.net/).

The piccolo server probides a list of all CoAP paths:
```
coap-client coap://PICCOLO_SERVER/.well-known/core
```
where `PICCOLO_SERVER` is the host name or IP address of the piccolo server.

You can get the value get the value of a resource using, eg
```
coap-client coap://PICCOLO_SERVER/sysinfo/version
```

Some resources are observable, ie the client gets notified when something changes. You can subscribe to a resource for a period of time. 
For example
```
coap-client -s 30 coap://PICCOLO_SERVER/control/status
```
will print out any status changes during the next 30 seconds.

Finally, you change a resource by using the put method, eg
```
coap-client -m put coap://PICCOLO_SERVER/control/autointegration -e 0
```
