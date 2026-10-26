# Sessions

Cookies vs tokens. Back to [auth](index.md).

```python
def get_session(req):
    return req.cookies.get("sid")
```
