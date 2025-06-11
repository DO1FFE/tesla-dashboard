var currentVehicle = null;
var MILES_TO_KM = 1.60934;
var parkStart = null;
var parkTimer = null;
var map = L.map('map').setView([0, 0], 13);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: 'Kartendaten © OpenStreetMap-Mitwirkende'
}).addTo(map);

var carIcon = L.icon({
    iconUrl: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADwAAAAyEAYAAABQZmRBAAAAIGNIUk0AAHomAACAhAAA+gAAAIDoAAB1MAAA6mAAADqYAAAXcJy6UTwAAAAGYktHRP///////wlY99wAAAAHdElNRQfpBgsOGjFOs0WgAAA5ZklEQVR42uW8ZZQV57a2fVUtX71WuzftQOPu1rgFDZLggQQJFiBYIARPIDiEYMFJIEiCBwvu2khDN+1Nu9vytaq+H3uf95zznbO/s+XsnXeM7/5TYzw1nlFzzKvuWU/ZFOQ/i3+F/u0oApCHRpoHHHXOtFwEpikXuB0HBNyp/i+J5v8XEv/pR7BxhlYg9ytt+eIQ0NA6s+AkSKEZx04Vgqv7u1bnyoB7fwa7hAbyxP8w/wlbMYDc1xlougoslXOlA/9hv4SMC7jPfmIBM6Wk/RVxObBRAWTxhlN/HvvXnOb/Uv3jgE0UYwLKyaH834fly3IzAGfrzE6XroHjkycZC2qAM/7l2rVacIx41mTpDeBr5/qqeeBoUZqccAhciZa1xdkgvVdVN2Me2Fcm+u6pBo6cvA/u5oHrM2eseSi4fre2Km4Jzpl5LW+1BadHYZ/H24F3uBEJuDhHK8DP2r1gFNDT8WvlSJAvuepbQ8F5uHD5owyQZpgysvP+HLTwR+P435fwj5Zo065ivWkXyEtcY+QloG3hcU3XCVInXuv59Cr4rC7oNncG6JP16zMHg1iTAcIPIGwXJgs3QdEnMvD9eHAOs5woNoHspT7hdx7kyYUn7p0GOdVtZoQZFJaAOS0vgUtX5HicBsIs89GCRiDcl9zsLUG5q0H+PF9QnHCzh6wH16GswPNp4GpSEv9qIQiS76QWq0GaUuj2YDaIa3Sl/mNA3bnx4kUfAd2Uu92ygJv0la8C6zghtAJUqNH/0Zj+CMBj5BzGwN3KXf3vmqDIlHy+6C1oXxvsuhAoH5Dw5blh4Nm9ne7Rd1D5q9BceQXqjzfOL7sMsru9vqoEtJNMC3W9IKcq4zd3H3B/4bm/4geI/qpuUc4pcLVT7AhKAKdU3Eq+BaZWWUfC9KAapo+pXAGG2VHNM74H8WfNZq87oIiTLNZ8kH6x3itMAdMQQTZ8C844ea3QB9yyFeekYSC4akZM/ATEbeoXHhqQt1VqUhcCUw1jI2uAxlpz+2gtMJihwlJAi5HqQHW6sOaPxvbXS/m3TrBdrvrCdg2KSA4sMsHThB/vPp4OpcHZm8pnQf5rdS3lMUgKqhOq7QEJ1mfjOrhDfRu28jZQ2K9C8nkLsS1zWkrbIHBZWZxwGxw7pZrKr+G9j/omxtuhfNGrdtEToNycur3eCTCdyT4TswSEAeIUlxmiMge03RQOzhjZbDVB/krTR1VJkLjRJflXwiOnc0ejU5C81xXi0w4m3lH2eNALWniJi3N/B9fB59/uzAVJUi0zHwAOyw7nRpA9PaX6a8E+gaGyA+Tq6gyv6qA+GSr3rAXCcUUXzR9N7W/Q/+zgyXIZk8F0vLjKdA7ij5yf+2obZGy858j4Ge6svtY9uR3ENdN11IbB81T9AW0smKqpna6mUD221CdlM1T5COWGGNDMUL4JnArdYis/ruoOWUHqvaoF4NNMF+CRDgNGut0J+B6sj827jBVgeSJ9JTQHSwP6u5qDKqKG74MEKGlc+8Srj+DBYvPa0F/hdYp1rH8p5ARZVxjfgO2yraGyL3zevmJTbieYPtjS4219UD1R7nH0AfWRVlfSykDVsuZHBWsBN2bIl4EEzDhAHkE32Q3kUQHtuvqC0j3ivaEGUFzxXl5/LIhjdVcDjgPqPxrhPwi4TPMustQB5zsv3vmbBySoEiMKF8HjVOcIMuCJrygqekORS1WkfgLuV+328mBoE5k3/9504BNkeQU8SAhIbPUBuIxKP4/NoNwnf+esDqqP7VfLtoBPiXZ2xYegaK6V1Suh1E2ucB8EpleuDXoF2O5L11S1wdmVrvIhsGvkxYoeINWSz7MWRK18W44BoStO6QTo5jNEXgVtwuwHrXehY23bd5ZOMLKOcXPWMPA4Wat77gLgne6QfR0wWZ3nWg3CBvUK12MQHmtWOz4GxfNqjpJfQYj2PWcfC8Iv9Y8tHAOaI9VzRwUCn/85UV5/NMr/Xn+xRDtn23yd8+Ful+3ynVi4lH9vd8ZKePSh9pKjBpjWCpK9F1Qe1w0NWAPRn5QPS14BHefnaK65g+GCo6xqL7wRvK7V+R7ULaQiRxDodpojMkOh4W/F5riuEJpsS06ZDsVDIt2qaoI91X5UsIM1T+mhC4Oqbeob7q2g/H3FCO+aUN5WOO0/DKoOS3P914Plvkvl9QvYP3EuNtYGV4LrrcYA5g7SBaUvJLZRhmqOwKA8W3zVKCj5pmizx0Wwqq/XN9wEXYH4JXNBXWFsZ5VBnRP+YcEmEMt1v9gXgCs8riBQCUqx/rxcHxDPa3afHA+21qXXXuhBEaDvHhwHwgv95OA+IKTptwW5gfiL194GpcAu9QjPLX8c4L/o4LI77zaWTYVtjz5M3v0BPNmVPu3xKnAuVWwqj4SHfv4LWwdATEZZcYIKWsQWvHmwB3QvnT+YlOCor0jRBECSl8eamjtBOi4HSXMhZEPF7GQJvAsdn1oPQNa9WofZDnHlnQKkn0FIkAtQgqK/0ymvBeVKZzIfgiLXuVD+CZgtHxBKQarHOmUK2MaIj7V1wLxLqDK2B6u7s4k3YO1mqe2XALLSvNknHbTRVpWPGxiXqL8P1kDNLVHV/Tyh0YvGd30qIPhV5J7KFeB+1ng9IxEMOkf/olLQPc9+z1oHvAe/PmMJgGo7KqLfVIKyY9Ti/BwQn3q3NI8F6gsTGA+i3e9uy0mgbt3y7QYByNXNCzz+xwH+iw62jipTW7zhaUh5cd51KPI2b03rB1ED1O+L6yHksXl59gTocD73y5trwZ4mz3Icg4qRchIHQDvFlW1vD95TSla+XA2V91ySdSs4r4hm1RiQn4seynwwFpU8kGdA4z7XPlfUAsdMjYYKcLynqeAwOMI1/owE+0btXOaBo562vvwDWO/r7koNgEO6Daa3IAzUVq8KBY2snp19GDy+F/sp64JW8mwfORoMn4cEtN0AKn2oqsZ0MC/wGVXNC27OEI3SA7D6WCd62sB6wmwNzAfbetso+2yw/qqNssyHiJXtmjkewqJAy1eufGgcnVGvKAYEN/s41W0Qv9a/FgeAcrxfQIuLIDeqnJzSHYSPFR2094Hd6taerf4vApz5e+6bosfwOLHiZa4/BCwSGys/Br+zlk55JqjTvDT3dRI4z8mnnM/hXbwU4PABHtBB6ADWX6VZUjxYPpPfdx0EXBwRPgXnbmmU/BMoNguxwh3wXJyfpeoB2m/LS+RdkBzSNE0aCCU+QbvsvcAeoHsgfQsupXKBmAauB8qPaQKuOGWSFA/SUsV69CC/EUaxB3iBXdgDwvdCD0UnsG4RcjSHoWh+5XuOxlDRMrnti9XgaP/m5tNVII2SJspXwHxZc7taLsgughXNgUR5jrwSBIO8lF2QGaoaqEqC9SG10gccg68m1MquOAPej0y/Z0+GJIdX52YTQPW0amnhBqjTRYx/eRC8Hnt9UX8SAK25/H8R4OJ46aDlZyib6yqztQOvKYJG4QWaIS53S30IslcMSt0P6Zmu3vYRULpMfuJcAixglKAC33HCEF0PqPu56mvPx1CxU50vnALxfWucZxwYdqoHq9qCv2Scp94Osstjptd1qKhu663PA4ta+6h0CFh0QecLl4JD5Tqdcx+UByqGy/vAeKi8hucowCS8kO+DvErYLGeDHCfIcj7IkUK5eBusNyu7C+/Ac7vi8/gE8Nkl5T9sArRhmvMGFA3y3dq5GVQmGr4LGQ+yrxDqPAjmGfqjihvg+FQpCL3B9bGzrcMLrm5I3WJuAH6D6hV+lAD9qhsi7z2D++3Do0ekQPuhxk+DMsAtTzta/z4AZ3n+rwf7PwIOmBz4q/dRMMbqotTLQdvcsl85BDx+El67tQT9UnGjKgT8jyo3+ASB+ajo7zoGitH2VcJsaNFA3ynkKdSYWM/d9zY4TwZ4Kq5ByfqKN45A0I7WLNBuhNKLlR0D9sLD4/7TG4eDc3jPzo0WQ8PxPhfU4WAdVanL7w8Ok71hcgWodpVk5VwFP83xWpZWYH1S8MrqBlKsIl8ZAizhtPwSqC/05QDIXvSTXgI5Qk+pL8g/Ct+zEOThQlfFCXB0VF039AM5S5iXMwXIxIcfIME95rnbOLj/Qbe0wCPgaqYYKdwEU7ypg9kdzt5NbqL+CbQvGvXtORG8Vgl3yYDEzk4f2/uQ4VW03eIDrgk568wiqKbmx1tFaLwuoq13ANQbF53jvQkUjcVFwuB/HuC/uMjKD0m5mp0IZxpOXrpmAAQ5HiakD4SIDtGt1fvgbh+Pvopm4DNVrC2NgKZhnjW0cSCsKOrh0oOmrVd9pQbUp/yNyiNAE5Qsg+IjFS2NyfA6LtMZ7IS8cyXP3fvA2zVdh9fSgSq3/66a68Dc+tmoh0chMeNwydkc0P6s3Kn6AOqn9k/vOQs6ZJfd9eoDuedOZp9tDMX+FXeLu0POC02UWxpY4+QTcgiI49ksOkDxCSXiZhAbIwvfgTBWWCRuBOGd8FDoBMId4Z14FRQvqBR6g2uqcrD4Adz9tEdgiAWKB/Y+VOMYyBOl63IMZPXKX1kyDSKahzTy94QmP4ddDxOg4lTijrIM8NxQfttVHWom6vtpN0CT/RHdvV3QsFZ1k09/CKjyrtJvAsGXN//nVutf6WDtATG+bCV0CF1Yo2FHMPx+VeldHYS6iQszBJBW6kTVaPhSV7TEUgua1ihfW+GCVY2if/c6DFqVqpfwE5hP2wpVP0Dyw5yF/npInpp7PmAHWNW2jSonSL9rbYoHYLkW+p7nGVAMrPAo9YDbR355dj0czKr0qtffgv4LxeeyAxyvzmarQ6Cl0P700IngFu9/u95bsM8tL7y1EUQH3bJWwIPE4N+864P0XL4ptgFzB7ebqi/A47y5q2M4eLY2LXa0g4C5Fctt7uD91LTZaYOiMPG8MB0snYWT4n2od/FapGsI3N3s69QPAM2hjpbo6tBma+B3NX6DBDE9LrcPvFj/9lLmTKh2vXCvuiV4OOx9xfkQXOm3XFMLvJsYdmtOgsJL0AnZIO+T+/EVCH0F/hDAv29MvJLlAZtOf3ftUiXMmh8r1e4FjYc1NhXtgZFTs6q5Awkpihi/DnDG/10d+0so2GLb6xoLlbMqQvw+gpczMtODpkJRn/JAw06QP+eZfAbE58JoKRBcbdXL1O+Axqql4gKQXrlqSsvArbHPGY8kcB4JHVV3H5RXqxhQeRv8NtredxsKWv/cXHMCWKsUDTRvwTnA09XwGIRn2mtlaUAfpz9tt8GLCd4wEjzvc0s4Bt3uF1yr+A1CPqkMtaeBT47dKUVAdkttmeIYvMsWIoRlYDvumixKkGFRebnFgKmicI3zCqQEJpdmdYG696vvqHYUYhs0NdZaAFkd80+XnIHKPKXGVQA37t9sW+QO4gbXLfkwGKx6h/oH0DfSXVB+Bp7xxrWaX0Hsq/ynvrP9L4CrNpVPr3oBVx/uPn71LNTZ8+BUxUp41ipZSHHCxv0tL6kmwrilmlNFVhixSHZptdAmx3OisQfElaWOU3WCjA35O9WbwPaJ07O0NsieZBSmgDSWAskJxn2Ky+67wOd5VR3fWhBd+6Tt1XIoGtNmaFg7qN0rqE/EOKjqrdS4TwHzLoskbIEuP7LfPxIsm/KFqrZQObOilfk4yFdFrbIXFNxWdtSPA8/cpHopYdBgoCrKPhJc51ReyuGQk279wj4V3G4bpynag2j1rtJdBsVzv2nGXVDHq/KEywimybkXrOnwJNLZseQyZG9+u8h3GkgRUpT1ErysrLybsRocHzuynYXQ/IO6kdF7QZgdUSTEgHCuXkCwBpyD3xRVqEATqr+kvAbRvYMVHpGgeqTsKub9HcT+Rv2Xa/CFsUf8Ljlgd685p7aWwsBS6yxlMtwxRn/sGwbfj6h7338B6JuUlReugq6PS/YWTIbGDfMv6HLA/5n+ifEBOFpJBrEfpHxYpBJqg/NXaZdwCIRsakpPQDCSzgLwtKlu+2RDwE/qgQGA8pD6rnYbWNxDu3pZweOmHCBLIA8tulz1FpzNLfH2bWBKtP9gKgJTtiu96mtIOW87mnoEXu2ztHw9DOxb5Er7K/A8qLrruRz0SxRK/Wvwfqo5olVC+6+qDTJcgjbvglboUsDu5WzliIe0YWVH7C8hPaXsVykdUpaWtpRewMNY/dzQbfB2QOOQGt1ByIjapG0GcmnQcUUkRD4LH+f3K7SZXl9f4w4425VvdEaAObwCWy8ompkwofQWVDtSPN+1FCYO7DkmZjW0LKrbPMAJipriHKH/P9HBZT2KhpZdgrOVB7r8ZgNDZ8c3rAWjB9PFMRAyr7KjfRVED6z6xnYQ3OrII43VIaJn/s1yGXQLc80Jd8B/QniaZgfUi6pxP2wQ5NuD/d0Hw52q1E7y55C9qrBeUW0whZrfVDwFxyxdlv9MsH3nlmkJgMAQ+V7IYFDOTWln3g2FNaVQa3+wHHO5TNfANk2aZasNkru8XboO4i4hU5RAc09MUL8H+ihxgU4PlprOWMseKBlk/6pkGjiHqx67vgLDYrHKeAxencnSeyRC5d3ip35HQf+eYjZXoLDS/k3R71BQbGtVeg5M4fYshwWCBzpK83OgMDm/i48BrM8a9Yr8DALCwjZ71YTKY6aH1glwe8vzorddoU7rgObB90Bsn5VhuQIRhc5ixRko2Fg2tuo8fNH5+5j7X0H3ipa5obEwYlOPtzWzIGJl0FZjEPAbm3j/f9HBD09cNT4Oga/7j5+51gXRzxxNlCXQaaJ1nC0RFD3li8IQKBqt+1U5FDQFLr38LXgcsDtdc8H+qzzJIULOfrtX9tdQlOmnkp5C8/ntFtXPgNpwlHuQf66yt+MZ3K+bur3iQ3hamHiv6FuQYoUktxLwTvFw1bgKgV0MjyM2gWqbKKhPgtZDXKydBtqxipqa16D5UPxaewvUN0SLuilwWn7mGg4PHOXci4JbAVULHpZAhdnVpXIwuEcoz7svB51e3cAwETRzFZ20NyFggJjl+waC+yrloEjwPCq2dh8MREpTJQcUb3JMK30NKYeZZ/kMbmzxvRqeD2U5gQuNI8DnUqflnhLUdWv/Y/hr0LRRrVftBvt652ynBaK7Bt/zk8BruSVb1EK4otTgmgq1u6l1mnGg/EUOIxrUfurpiuPQYG/19j5hoGupGavs8L/o4Nwu6T/mGUDdRXKpO4HmKNekMhD2yfGUgmwW6hEFvt6WBc5VwE7q4gmuQ9SRJ4I6UMxVO6GxYJxVpwrSVroNcasPu7ra9ri1gGkDjOaKOqD8yL3EmAiOxbU2RI6AHt3DfIrioMyvbLRpL5Q8Llxd1g+ca02dU9eDtJQ96rugGa674jsHihdbjlTmgLTHsc3+GrSthR56FdiM0kn7QyjMr9j2cik4DiryTVNB7iWWy9vAsVC679gO2nJDN0NzyBjbLKTGEUj4zM/b80cwHJKuafZCjQtMVO2HntfERxmzoX0P3ArOgljHOdh8HzqWO8+XVMC3gXkLG6+CvBsJJYoG8HivpjLlMtQ91GBfaBTU6Ru1MCQUVJnq1spHYBujv65sD+lPDO9LP0H2vKy25iqImWDLExtC935h/oG2P4Md+U8o0aUr3tUoXQeqXcIb9SNQPZU6m7qCOI5KIkDehwIB5PF8igaYKUTTBgznFd9pIyBgg3aiMRU8xyq36vpDdIwlVEgE7xqJXd30cL2nUuOMh6ezA1pEhICpP1NUd2HBwsAK24fQb+/g8+2Hg71Z+IWocMhv9OZtSjGUz0nfmH0D3EzKUQp/cAyzrVUvBFezig9s5UBevo+lFEqloseuxlB5JO2wnwhFdUvWlq6A9I8086RuYH0uFVqHgSG7IqGsO/jtexmZ0QOyktum6WtA2oOGRcGlkFylPqg8DRmb3O+Zd0LHGprUihnQpZPLkXsPhg2Rb2TvAL37y48rNTDneVr3noPB7G7poa6E+GMpD7NmQmmTitamNGiytfacyFkQ0Mx7g3s98Omqv6meA80H18cjEgLKK0ukKmCmHE4GcJVLpAKd6U7U/wJg6VvHcmkVKD1yFylLQLlYGK1wA3WaXCLFAYc5zmCgj/xI3gXq/mK28jz43dZMMH4OviPUYW4vQH1QyFHcA9cTQckSeFXl86HXTCh6aXbpYyHnoCan8HfIKWtX3dsF/UaWvQnIhKzXyu/CtGDb0fnzplbwdFSrHRgHHnHtvVsEAF+Wf1+hASk3Nyb/DbiKszJyj4I0JbdH/niQ+zhfShdBrnI+LCwD07azAyuaQlqvy5vddkHuRPlUuQWsXwgRxIHFTUxw6cEaGJ7gNwY85rwbWvgzqGqYXlvdIS+ywe/Rv4MzzNdDOAGupTVfVXSGPQsSdtdMgR/ef169wVbwGpI7yzITFPVzztrTQCpSvrTfBFWe5xK1AbQHNTmqfZAcntkibzlYztpa2veAY63/Gu8foOIZn8rJULfKMFaTAy0SNJtUvcG5hknsAmVnYP7/AmB7+8pp9lEgTCiIZQ8ou/KtIhFUBySV1AUUC4Vr4iLw0Kre0x+GgHJtL+PPoN+riFCvAGGnbGY62JYodwtGuJIcle4fDOUV5kKffEiaX3X95go4VdrhYkwqFD9x6+9sCGUp6nEFObBuQauZLT8Gz8hqTQJ7/DmqjwDEP90frvDCExD583ZajY5RjcD23pXnt6JAqp11LicdRJequeYcRNSJWiOfBh9Jl+SnBp3ZMbm8HdiiFFfFT0EVqUjTnAd7R3sbxxt490u/35tMBe8H2uXl7UExsEohD4DswyVf+V4Ba22bXjMNDFOVw0zn4XZl4fSQbvDuXu5jn7kgeyhgDwjz0u457kPlm8rBFRcgZ3O76eI+aHKktTLSBG7Ddas0QeAcVyGaR4J2fnktizdUFWoNGhdk7zNWGHzA7zcv2WsTeGB4oxsPQG18/n7Aolwqb5YdoDgitVe8B+oMlipTQX1RviHPAH9BPdmoh/AU/V3v66BvqGijFkGsI/0kD4DSy7o8xXjY2qbVvdA8SC9RukK7QsXO1C9uFsH5leE/C3YoHFz+gWMJsDW+e3o+JHdM65baBdb+mrMo0ReKh9hG2kP+ioi3qK6r2oHiYbXsoHGAvxAn9ALayIO18eBnC9jmaAABHj4DvRJBOVv+VBwJ8iJpjasEHPe9MtwzQZSE8WIk+Ny4n5rWGgQ3j+7K9hBTWKthzjJw/OCyKUMguUmhI6QQImc2XF7UAgYNnLr0SQD0PDZmbPxZCIxtY7KcBXFz6/u6FBD312ik/hwq2hQ3MLeA+7XjOiRnQXZMQY/S86AbohQUcyGy/MdFt9yh0edzNh7YC16jvup/2B1Kvpneb1tXKJlz4MAVBcg4SlzD/gHA6lLjt+p4cG/v38KYA7r78iO1AzRB/CL/DBqN25eKTqAIUlwSY0Bs4FopR0Pac+/F2pkwJ7L37Yhf4M4s4yJFNqhqPbl9ciEkvXZMevYOSlZ6lvkVgDDDts1RBvJWxzXXS1BkWBs7rsPTdhmnc3PhwvbMddkX//rAFduDpgWuACFRk6tzgtxQvqu8AwZ/j+3SFvA0e+UUvQa85FBxIsiNuScfAtUMeYuqFlSENepWtzVIFkWkaALz04ff2I+CJlGpdLyGDtdq7n3xGnIsZT6+s6HyvCVPfxV0dn1TuwiNdzZbktYWBm1979LdMGgbFKl8mQ7uvwudKn8DYYiujuAJTqVjlLMjPH/+8lbyJri+I/Vx1kt4bBwztsNyKF/R6FBkM4hc37+iTQcIavB50uDjwFm5GZNBfs/6kf3hPwBYMUJdpXgPjOtCTroPAXeVXGjYAtVW1rGZm4Jv+rLssrEgRo+NlqLgQUTNpYbeMOV6383Rv8G18pAwdTH4bb025sfVkJVVkHVRALeG2kthc0ChUMTq5wAlhLAfBJ3wMb2A+pKbvAmsXSonm+fBQefbXamPoMLNHu9Y+ldEPtXDSx0DQopXTv54oINz9IkiUO9VlT+ZBMaGXoczNoJQk2+FItCoFFe1B4HdVTsr10KAXfskcAqYre1jajwCSZS+EZZAgt9LfWBDMH6ke21uDM16R7xKyIGqGdaRugkgzKGEHSDrGckHYHR6HZWCoMHd+tHu2yF2WHWdzz6I1Flv+rQC/0LbTOkcLPjh3bq3KeA39WmTF064/ODdipym8GvtPgkNfeFBxe/7HlcDx+P0UXnbwXv8qAtd7oH4ndFDN/GvyMdf0P9ZRbsXV/vSOBe0WYruhlXAzz4VYjboD9evY/sJHoW18s1tDjvz6jR1XYCkmNLZIVVQ/dT1SwkPwN+Y8UFWJIQW+PTqHA3KOYZ7bQOAHIuUHwv4qRuobwPIbfkJqGSPfB7EF2aH1QMexOSVFS6D303ZP+ftg4FELgtdDBzhlDQaXK2lFYVWcCxz+L/+GOylzmevLoPw3KfxxTxQN886cn8dOCudo5SLwBHgGqv4BLRT5GtuvUF/TDnGrSaoG5qmmqeAcuvbb7MqoNHMpp7G6hC/WLte+wlUhOTl63vDnfi3KfWeQJ+zDS/fWwduomav9TFUxtoeaDeD4rF40PECtHHKu84w8GpoeGgdCRqvattDRkJOLaVR+SUUNSo/UK6A5rddx2yTwDg2pklIbbi4xH+o1xkofeCb7rkWruePbRe7DfD79tzpbGjSL/9S2WDwbj06vcsU4JUSxT8E+GToPuMw0LRVHdIpIV9nKTaMA9cEh8rZDrJfSb0rQ0C9h4nJz2HA8WuNfD+DemVPNREF4BMYNHX6WvAYrusb/hgyG8mDy/QgDygdHh8N9HU/FLwXgB3oAA1fCBNAPmb1sf8M5obWRfZLcMD1ckpiEnQy+98pTgRVS3Hiy67g3OZMTf4ZpN2ytfwzIF9sL8eDYlhQrtdMKNhzb57XDvjt62un/XfA45/idOIcUI3WaBWjQe0QczR7QbXOw+DbFCS3vLF5jUBhyVFEpEDs8SZfvTgK1yYqttQogRJXlcL9CDz4NG1n7QCoXuD/adZBCDO4+9vOQtPdejdfB0Qck494/wTBWuVuwwZQNtamJ3hBnY9K48pmQf7zvFomBVR7UdGxXAEl56xWiwHCR1efExYJUjNeiR9B2VNvP69JcGPqjMC+/UHZfs6Kg9WhTkT++LI14Keb4da/LwgWnUnT9O8A7FO7lo/Pc/CqEXTacxPkb6hI9YgEczPb8vIdEPqNLl+zDfwGZZsje4Fj153T1lTI+dl8NC8ENHWMzuhDYGwhlwnvAYG0lY0gfFN2oPgO0DWk2G8xyJdVo9XDQfCXvnFlAZuKDpacATml0mkcC/eW3ltlbQmvuoZ5/n4capQG9q34EN5tTxwtWSFLeD3dtRbMUytjpAdg61mZrRgGz7v+llC/EgJXul6WuSCkwmguawKlPpWiXzvwCJSXqSIg91IdfeOTIN2ofarBIKj6OHuI8gL4BcW0CB0IvffWi3+QBaUx5t8Na6DlNd8j6mxo8sJ4InQjlOXLQ8vToO09cUXD62Co93JhuTc4Bj+slTYU5LTMzsW9YUAn52pXd3AurxRd3aCyMENtvwvVJz8ouTQOXE8ev8rVg2yPvaZUgjQl9JTyfaC/46XcCzwiAyZm5EKxx+6Idy9Bnq7wEo+A/8Tp2f2HgLBDG6JK/Vsc/C40x/0ARD5p1zJMCclxJ454xkJOtcKGzibgdz5qGZuh55PeW7vNguCFMbYOfeGXVxtWnCiHuFlPDj8Nh3wvVePABBAa6E0GM+Djemm+B6wvTim6DcId4argC8KoolEFfYGOlV+VdwR5tuaY2BDK6xqu1zBB5sGcCMVpMLTIqtBJcKnH7qSKzvDaGveu4jpYO1d5ymMBLRreQcQP3gNsY6HZq5j9BWp47axaY7wMPbsKNkM6GDrwpTgezo8OSgoJh/SU0KiohyC6OTo4dsG73JQFHjngF2Fq4x0BoW5hhQ+/gzb9PKoF34Km0faPvFeBZY9he60XIAxVHlGNAOZXNyrHgDzi+aTMjpAfV75TzoJij4wq6RQYjr5tVtUc5BLphN0HDDXqzcodA13PauOfFIAuuPSBuTaw0DRSngXMZp3iMsh8dDxYBudi27qaJ0DZKMZc6wpgFc+I9QGY9Dc5mAvCas5B9LkebaJi4abXqXCvdCiWUptV+UBdVZt28rdgaKaaID+Dpjc7+TQdC9XFBjWiVXDBue/8BSfcrXfIdKcDFLtK03NHguir9nTcBHFH8o3EIyBvlUZLLwG10JrTwFX5huwNopfCvbg7BLa314heBZlT9g70ywJXbH6megmYXe9W5Elgf2vOqvwNxI0KvayCtociDuXFwftr6tVLrwPlyaZdYl14uduqqOkLfrcFh6oI3O9r9snvQY+Znu2SvoM9b5Rz604AZzPXen0sKJNVFyzdwejvrUi9BkGfezS0eEPEVMX6oGSQvihc/+gDUL9w6x97B+RJac3LOkK59/GHz0PgVt9r78rvQ9LazFXKZGjeyZRTVgaBU+rGFn8NHvs7LSz9EfSHa14znwNhiXq79DmwSLIIG0GuI9djMHBKaVLVBD5p5D8IUAr6X306gbKXdqV5DQib1ZPY9teX6P/yutAZZFrobALH7k+vPHER/D2M2hsroPHMhffFj+FlF2cLz3fQ8mzAzYVloD0iPtSNACld2imlQ5Y5uU/WY0hYFJfy9g2s2/FD40MCVO2uXGs6BIrbyjwpAdIq84NyfwKrYIyyh0FQ84AphkroNaP0QedbEGYq7RCgh/zvbT3zYyBbdjRJ3gdmi2uENQ1inVFf58yG5sWBtmw1KEXB4BwOT3JSPgy4AZq3ue7RbhAgK19wA4wLvdsrmkGu9otRnIQT5X6n2w0Ha2xlgp8dwpvFjLhUArrNhg/zFkLzNbqljYKhO6Kjrh+w+PmCQ7PAtd7+sq0XWGtcjc7rARfa31lpPQt3R6UPVd2B2LXhFbnPoOu0nldTokDfPcbDvBnk3+QYOoEc7dwkVIHormwsvwFuKdRybRC+Em/LDQG9crbqFsiJ1dq2GwQ0V4UY0oDO9i9MOlCme9xvNhiUjaO/+ag50Ec8pa76axz8bwO5biuVT6HT0WlTYx9A4e9bjsZvB+FC+qOiAtBND7tn2gzmQFdKxbegRUQ3AsQIcYIYAWHUJCwCsnaYbpRvhageLa/V3gKfDhrmHNgczmc9vbwnEI6FXPG7XwvkwfpJ0hfgLohK9wcgv3w1OTcN8pdLa/O9IfB4SJO326FJS7/BtiAwq8qb20aA/rLrTWldeLojaY52NqSsLRihqQB5sq0icDZ00robxN8g8us6i9RdwHVbt4mr8GJKtXzzXghdEfrqWiIIDSQPuoNij3KULR7UBQzSdoSY7ppV0UNAPGYylJWCc1vawKqR4Eh/uiZpEDw6n5yuHAoP3LJWqO9AaCPXa2sPaK1ovjdrDBjGNrxTuRVcIVVXlMWQJxxUB00Ae4+cJ9qOoOhiKHEeAcVIw2hXEijC3J4654AQ5b5B2AIvNrZPr5kGpTvDN0VtAY2vuMOZDcq21rf6GxCeYZhY9QQaxgdu8gYUdYXP/irA/6bAmEbfBbYEzeiuoZ0ug2nvxsuHHoFPQvcclwgc6jm7eAbQNYCA/zDP8da52lkCXrHG6oa+8HWr2eLkK6DeqP2aVMgpvdc8ww44/R/bdwN75a/ZAp62wkrXUgj3U6TGeULL0JYtLQZwi6gxN/wcKI6qMo3Aow8v/pg6Bk4ufjE14C1IA8WJ4iCwhtHLZyy03qu4p3kEnlP9hoo9ofRZpzS5NohV8gw+gdIVXiNcvUHhI+I6AeoExVF9NijOC5fc8iBgvmKvmwKCHgixnndAal828ZkKXMPf+bjfgGeXskbZusCvNxKu2i3g/sqhVLaBpknS3vKmYMjy7Wb7CHifcWwG08E3T9xcUFHjwTee7UHOtSWKKkBBDkMBC23xALJYySIQBsgZ0kDIPVmWrH4frm758IMWlSBuYCy3wONN6ZTSi1C/1pGGFy5CcOc27YJjIPDNsAax1wGEF8KJvwIwDf+08Vz6/rz2q8A+Lyk3+xIIOYcVl0aCJklR8PgMcHn4uFq/AN3EPeIlUN5QdFJYISYzenbEtyCqhJvCr/B4dcqRO6HgP86jY/BYcJ+i3OP5PhhXZO+yX4Nxl2XRWA6deoyOrLEDMuId9Xzy4MD8n/JN98C4XrXAugLuRKcvbpAMZRvdP1Dfh4DXwlaNHloesK+xqKBentrHGgdiQeP6wmq46t7nbJUJnG3Fz2QfsOVryoUAkDtJgUIw+IzV+kXFgDJJGKrJgpijykH6waA9VWJPnQmuj9N8Mm5A2bWce8b9cET9WlNcDbJVJm/VA2jTVq4nnIHgPrpJlp2gTPfe6RgLrnhLHcVMKFPfKPT6BeT2NqcwCfhZsVceBsg4//uOAtJprkN104v6L+dCZlqtQ9GPIHhXWquMi1DT/cncODfwGpofUXIYCgqvvq3fE5Sj/TrXiADfQd0IAej/PwH+t4v0PA3K8+A3ZPa7oT5Qunb/LsMQMPW7nnnjS1AfaRzXxAwq6lIPEMYLLYRgEOAm30FBZPnYnCxwhrg8HAHgk2mM9usPrhGmxiY36O1d9/2Yj6FGncisluvg6picKJ/Z8HTqyajiQZA5+7VXURwIY+VPbCFQvbn2pHsD0KiUWdozUKuGSVNeDtEz3BOdgyH8SotHmvXwQtflR9stqOxv/FHaAXSR50vrQC62zg2uAvmiS9Q8geBUz/AG40CMl2ZZ6kHUZEWZai3Ia3PTLviBPDFhQOV8SLtekO+mgTS3sp02L/CUZb3iEoR1tq+0eIFyZeA+5x1QRLjHOYvAfPNNqVtXMD99Xc+wFJghPkcGYaj8mmLAGysukDcJjQkE1LiQQdaJnYX64NmvqKpkOPT94gf3Az+Cuq71rn01yD7aEv8scHwWUtTLDkUdVQFB9+DmzK87nPOCZjUNP7c0Qav+rT9o6PZ3/OEvm5yjpepgGXjH+TQIlHd1zeV+oK5q0bC5LwCdGQtyJu3lS1A2t+pUcTg4M6Vjzt4w/9WupPEdIThYmaRZCP0C61yKvQKnP9manzwcSmrGmZ2J4LFceOq5G4rWWg2ZNaHuepfVdgdCsvmQD0HbTvhJkMC9obGbOBUCC9utUT+Ax8oPl1qPQmph1Le2iaBM0G/UtQfVEEEt7IEiU+GTWkZQt7O/qhMMvT6rP6RuP/DMkT4t2gZhBmurjMsgLL85Yfc8sE+/uSYwBHbH302ybIezQtKiqjEQtVg7MEyCPvmmoTZvaDCi4dE8AYI6TczPUkHOsV0DqqVA5ayHEe75IESKUbQG2whFqbAcHN3F6kIwGIY5CqXxIC8S2hIFuMlP5RlAdXbJHiC7VD4eFnDe8GrSaBW4HnhNa9AJSuNY6GoMiR1NijdN4IzSoXmyCmwNm6Zrh8GJxO97r/7t7/jDX3BTHhCTQX8plmYARQxlEOCkH6v/vSYIWs4K9cDriMHDNxhu9bvid/0DEN7eXqkbBY5wNvt0gmPeOaFPAPOqdxc1evBViJsCg8BxiDXOQKg3XrimSofqxXJd6ywQ/cRRQjJUu1azmToFvI9ErVG1h4cz+6yyjII3fnVW2hJAXsZPUh2Ieqso8m4G3ij2uy+F/BTr08CB4H3btq2WCbxmOI8bZ0LAJuurpFcgLjfVzWkKLp93J4WNUFxeskFzDeI65Dcs7gC+T1XVfU6BPl9cru8PUi0UtlJQ5wSOsq0Gy+LUSbp8MOlfTTNsAuaIc1kGgIsKeP6D3363KRCmqHxrGwbGeEdL1yaQq8sT5Uygk+Kq7jw4t7gvqTUSnG+9NU0vgrxCu9nvWygqdwQUJcPbM6b0xJ2QcUvyKDgBL+4p5+fMBY/6RSbPQVD1xFzbfPHvAPxf5MtRTvw34/54EAySm/OmFAmla5I7VFRCwG8NT/iOgfJC5cbC78BjZ4sqcQ/4Xbk5sdovIBqEbOVeUAtCU6ELBJ6VpktvQPSRf6YcfNyqn1NpwN3Z7KBqGaSG1gy1X4AXjRt/b90DYh6iMAtcDeX3uAk+bRShnssg3K4MDouG+1Pt7aplQc1tVVuuPwPPWdnh6k6g9pGHv5sENK4MLd0Csn+Oj1c6vM4s+MK6FIoXm54rGkO1BE2wdzYEnnS1tr2Eap2kPdaWoFjsVc+5Dcrn3nrp1RGkHebfxCQQj4gX5SxIWekRom0OcTt9V+jfQOPqhW1NB0D6XTyrFMCV7zYy4hg4G/psb3YCpA/1UWE/gjxOyBGnQd44W+3cgZDUy9z27R6weksNbBnwNFGx6N1UKP2cFeaZ4B0r6rxag+BivzDnfwPw/yCxvvij+B1EzRs43H8G5E5P3OpfA0Ldayib/wZPRz3odmc6SKPDsu0KILKos7YTaLtIQ50uCLjgddH1HSjiwhJU/SCleGyVYwq8KAzMt7+E4rs+s52vIPqUoTSyESgnMltRBi99rUsSvcGnSNHH8wX4txbCqw0En94OpXt9qFFu++byT+C+IXlv3ioQ6vh3iZkJUlnaZ44XYNOX/mh4CA/9cvuWdIWqRGdNaxZY4xUZ5Wuhzj3bN7QHXTP1T07AmVK+ThkOVVteBBk3gTBW7Ek+2IoVnqIKfqwe4+OrhIbPilaZvwfNBdePwgqwfhM4psMCcMZ7RTWuB/Ir8TN1Acgn5WquMZBlt07IfA9Sf7c8SekALqd01emEnM1icHkyxLcRHuR+AMIJ+RfhE0ABTABcf8r/Px2wY6vwva0BOH5yW2GWYfCQloETkyB/nKt7+ll4qY5celsL9sgx+YVl4BwVkGh9CsHTxGv2M2D42duOCE9edFgm74LKDZ6tPT2gTOHVM78EQt+oLgR9B92e6h1tF0BpK+lBxdeQ6rDfy1wCXucUP3s2B7faDq0tCurPsQ16VAL+D6V6qQEgdrQuM5WArCtZrusIUlgyAUbIzalozucQH1M4wOID8ii5neQLSa88JlnTIc/bOdNtL9SsVllLNoJp56tphj3gqqzqqFgCim7yI7kHXP25WpJHBDz/1rdK/zt85Hhzr3AcyDvIcvUCYbS9ZWkrQCkcFzeB9LEc6CyD9K7WOundIUNpOZG+HiSJfdI6cM4VhkhaeNhKuJzRBEwbhRH2H0E4LfdlGX9q5ib9B4P9swErWgh9FV5Qf5fbwHZ1wKtUo/UPgvwox7EMP2gdEXm7137QjG6QyTqQImcMydRBoWXU/gIjXDf2v+2IBu9Xea72q6Hp66vFfbpCtbo2//CJ0K2PIa1tLHj4EKD1hkCbfaAQBhGZqgOhx8D9ueKB+3bQDDbtzPCAFpXWhUfyQT0JX+saYKcwT9wL8ri8Tyt6g1Q7v7V2PsStyT9p9ofiUHNfx32Qg9VW5UpIrFbrdMhh2PhJ0/eDdkDCeM0X+kPgMGcs0+4G8TWn5SWQfcHwSO2Evfvr6Py7QQ1XWYjVBsGTTYL9S5Dn8h2BoB5cevjlDXBdLPV6egqSHlnGJYVC+ivLB2lDQFrFB9JiEHPxFfpC6i4hrKg6JNUQmxZeBmEoJuEO4PzPYP9lgEUX55UGUFYIDdSnoeqMy6tsGESc0GyqmwH+m1XdQyeB2V9aUrEDMKjSpBdQ0cg4QBMI1W3Px3etDzWevVjUYg/4tC//QL8Feh8xW2q3gKDa6sTAWyD3KD+SHgCaW/EzjxuhWUs5OWgnGCcojhtswJ6qWzkDwa2eK6awPTCKEI4DFfzASHDVyvvIdzWYNpn2K9/Aoz05Paq2gaST3icUii8EO3z6Q9VJn+Eev0JSfY+a2vGwLqDRz8GtoWCD9r6qFkg/CbHCSjj4uNZ53wBICfQwazZAm0V5nasWgbq7K1beDqKGIuE4FAwQH9h1sKnM8fi3BLhV1/bJ8zbAtD99Ry5k4c3PYLlNH8dReNhLvJYhg30eLZytQZiMi/b/H/n/ZwP+f0v3i+htuAHhSu2EOjKkf2qdE98O/J6oL1ULgLAelmX1R0JL6/3AxmZotLEwr/RHEKeJMdZi8JsQ0PrEGvBvVfH1lWbAOofCugt4P3fos0EgNCjMjp8BoamZc5/PBs0V1wfyr8AvVZdza4M8lflcBMFNWCzvAumFJU07BaRthW99f4J0e9mntpGQdLu0k20uCBFilhAOpnueSYZHIMmKBDEMxKlyqjwRHvgFrHW7Dd9/0+BsgAEuXg1b7vEVnD8Q4eHVCuSxQgfC4FWRj6zbDZYs1QNFFmTkKw2uH2FFgveWqh/g5D1du/K2cHWVmJf4A5SNZ7t5IYj1KBZj4U2EMCRvEmTmCY7SfSAsokpI+cvO/cMAq9KFiZoqcITJ8bZxUF7NlVz0BLpl6B+P9odWbR8E9LkO9SZUmt6dB19tcLWjByFgQmi9fbvAo6vf0WtXgeyysreRwJzcokexwJyiAy+vAu7CWSEDBDGn26OXIJzL9LplBmqZ3PL/1O1mkPA94M2XrAdXSNEL71kg7TK566fBk465fU1noaqPPck1GYRq3JEvQLArqXP2MfCckB9Xeh1YJrwVfgIhj+08gPPm8BOe5fDtkaYvgo9D1RVVA3EHCFZ5N6/g9AdR7t77YEuzyG90/WBZitf68sNwZ4m2gz0bxFO8FsIgxyUklpfAzc9EUuZCYRS/VJng8QDxl8w64HpDsNQAhBZIhP/P+f6He1X+vSpOcc7IDYScFEdF8nKo0cpU3PIXqOhx5/VNGYzVHH3nFYL4mgZlOsBLuEw5uHaUuXkUgSui+LV3LAhO9wDNKRB9hUfFq4FsVXdbHAhXVVcc+0FYpitQvwfMEOra1cAHsmgtB5Y4ryqWgz017nH9H6BkeO5U40ZYevbmueybkDyqdJttP4hqQeQzEE7KGnqA5YoxSHcVkjKbL4jRQ8V572fuLhD605bxIE8hlggQUjlLFvCM+cwC3dyCDYXbwOfgc+nFL1ARKyc4zkHVRf1tdQRQg1KswDkknoFyKEmKpRCQJHc2NoacX4WX5R+DPAp32R3wQcbt3/MpBUnD5cUQ6QjdHuwFv83aq93k+Besov+SjA5FoNcWiDmt+Kr5OFB0ED5UV4JX3dqrK1Qg9X5T6ZKAE3K0IQGoJ3SS3YFf6ODhAOeE7Bkxa4B3Wc8ZB4JaHBpeBqxQ/CbFAWsVL5y3QNCqvneUg/BWjSMdhL2aTvYsIIRL3AIa2Kv80yG1yrLB6g/FteSOysNg2GtcoOgJfEhdCoFYRH4CvV22ytVBUydpUs7nkGxp2t1wBixvDCt0PUD4hDnyLsCBl6AH/Ya8b/JTwJc37xJDQOXjvOhaBZ4xCo2yJxR2Vgma78DSSN1HcQCEFJ4SDfImwmgA5QFo7QvAUJf6ugZACDKeQB7/qf2xpJGby63ArZc+XHcJxCdisvDNH+hgnMg4/hykDKgQUIMsm7/Nvg/y86qF6f0BNZ04CujoxB1gjPNHpQUkVcWHhjlAkiwI+YCMBS1g45nQADBxni4gV8nH6AeYOEs3wE6yEAm40V2+DkKeMJjeUPDY3NvRFXKuVta1bwXhEAOEKMCF/J/6SAtIyMBkJssbwXLaWFN/H2xmvVkzGWghX+IpMIxGclvQ3Cj7rKIBKPQ20fYh8IOQKbwBBnCHZHBaxDfCEbAvV2aIXfjTM2kJEP7G7tWL2MAO0KVqf9UI0HhgnRsxdvh/AIq0iJkBxp0hAAAAAElFTkSuQmCC'
    iconSize: [50, 50],
    iconAnchor: [25, 25]
});

var marker = L.marker([0, 0], {
    icon: carIcon,
    rotationAngle: 0,
    rotationOrigin: 'center center'
}).addTo(map);

function fetchVehicles() {
    $.getJSON('/api/vehicles', function(vehicles) {
        var $select = $('#vehicle-select');
        var $label = $('label[for="vehicle-select"]');
        $select.empty();
        vehicles.forEach(function(v) {
            $select.append($('<option>').val(v.id).text(v.display_name));
        });
        if (vehicles.length <= 1) {
            $label.hide();
            $select.hide();
        } else {
            $label.show();
            $select.show();
        }
        if (!currentVehicle && vehicles.length > 0) {
            currentVehicle = vehicles[0].id;
            $select.val(currentVehicle);
            fetchData();
        }
    });
}

function fetchData() {
    if (!currentVehicle) return;
    $.getJSON('/api/data/' + currentVehicle, function(data) {
        updateUI(data);
        var drive = data.drive_state || {};
        var lat = drive.latitude;
        var lng = drive.longitude;
        if (lat && lng) {
            marker.setLatLng([lat, lng]);
            // Preserve the current zoom level when updating the map position
            map.setView([lat, lng], map.getZoom());
            if (typeof drive.heading === 'number') {
                marker.setRotationAngle(drive.heading);
            }
        }
    });
}

function updateParkTime() {
    if (!parkStart) return;
    var diff = Date.now() - parkStart;
    var hours = Math.floor(diff / 3600000);
    var minutes = Math.floor((diff % 3600000) / 60000);
    $('#park-time').text(hours + ' h ' + minutes + ' min');
}

function batteryBar(level) {
    var pct = level != null ? level : 0;
    var color = '#4caf50';
    if (pct < 20) {
        color = '#f44336';
    } else if (pct < 50) {
        color = '#ffc107';
    }
    return '<div class="battery"><div class="level" style="width:' + pct + '%; background:' + color + '"></div></div> ' + pct + '%';
}

var DESCRIPTIONS = {
    // Wichtige Felder mit fest hinterlegter Übersetzung
    'battery_level': 'Akkustand (%)',
    'battery_range': 'Reichweite (km)',
    'odometer': 'Kilometerstand (km)',
    'outside_temp': 'Außen­temperatur (°C)',
    'inside_temp': 'Innenraum­temperatur (°C)',
    'speed': 'Geschwindigkeit (km/h)',
    'heading': 'Richtung (°)',
    'charge_rate': 'Laderate (km/h)',
    'charger_power': 'Ladeleistung (kW)',
    'time_to_full_charge': 'Zeit bis voll (h)',
    'tpms_pressure_fl': 'Reifen vorne links (bar)',
    'tpms_pressure_fr': 'Reifen vorne rechts (bar)',
    'tpms_pressure_rl': 'Reifen hinten links (bar)',
    'tpms_pressure_rr': 'Reifen hinten rechts (bar)',
    'power': 'Verbrauch (kW)',
    'aux_battery_power': '12V-Verbrauch (W)',
    'charge_state': 'Ladezustand',
    'climate_state': 'Klimazustand',
    'drive_state': 'Fahrstatus',
    'gui_settings': 'GUI‑Einstellungen',
    'vehicle_config': 'Fahrzeugkonfiguration',
    'vehicle_state': 'Fahrzeugstatus',
    'media_info': 'Medieninfos',
    'media_state': 'Medienstatus',
    'distance_to_arrival': 'Entfernung zum Ziel (km)'
};

var WORD_MAP = {
    'battery': 'Batterie',
    'heater': 'Heizung',
    'on': 'an',
    'off': 'aus',
    'range': 'Reichweite',
    'level': 'Stand',
    'charge': 'Laden',
    'power': 'Leistung',
    'voltage': 'Spannung',
    'current': 'Strom',
    'temperature': 'Temperatur',
    'speed': 'Geschwindigkeit',
    'odometer': 'Kilometerzähler',
    'pressure': 'Druck',
    'front': 'vorn',
    'rear': 'hinten',
    'left': 'links',
    'right': 'rechts',
    'fl': 'vorne links',
    'fr': 'vorne rechts',
    'rl': 'hinten links',
    'rr': 'hinten rechts',
    'vehicle': 'Fahrzeug',
    'state': 'Status',
    'mode': 'Modus',
    'sun': 'Sonnen',
    'roof': 'Dach',
    'update': 'Update',
    'webcam': 'Webcam'
};

function describe(key) {
    if (DESCRIPTIONS[key]) {
        return DESCRIPTIONS[key];
    }
    var words = key.split('_');
    var result = words.map(function(w) {
        return WORD_MAP[w] || w;
    }).join(' ');
    return result.charAt(0).toUpperCase() + result.slice(1);
}


function generateTable(obj) {
    var html = '<table class="info-table">';
    Object.keys(obj).sort().forEach(function(key) {
        var value = obj[key];
        if (value === null || value === undefined) {
            return;
        }
        if (typeof value === 'object') {
            html += '<tr><th colspan="2">' + describe(key) + '</th></tr>';
            html += '<tr><td colspan="2">' + generateTable(value) + '</td></tr>';
        } else {
            if (key === 'battery_level') {
                value = batteryBar(value);
            }
            html += '<tr><th>' + describe(key) + '</th><td>' + value + '</td></tr>';
        }
    });
    html += '</table>';
    return html;
}

function categorizedData(data) {
    var charge = data.charge_state || {};
    var climate = data.climate_state || {};
    var drive = data.drive_state || {};
    var vehicle = data.vehicle_state || {};
    var categories = {
        'Batterie und Laden': {},
        'Klimaanlage': {},
        'Fahrstatus': {},
        'Fahrzeugstatus': {},
        'Medieninfos': {}
    };

    // Batterie und Laden
    if (charge.battery_level != null) categories['Batterie und Laden'].battery_level = charge.battery_level;
    if (charge.battery_range != null) categories['Batterie und Laden'].battery_range = (charge.battery_range * MILES_TO_KM).toFixed(1);
    if (charge.charge_rate != null) categories['Batterie und Laden'].charge_rate = (charge.charge_rate * MILES_TO_KM).toFixed(1);
    if (charge.charger_power != null) categories['Batterie und Laden'].charger_power = charge.charger_power;
    if (charge.time_to_full_charge != null) categories['Batterie und Laden'].time_to_full_charge = charge.time_to_full_charge;

    // Klimaanlage
    if (climate.inside_temp != null) categories['Klimaanlage'].inside_temp = climate.inside_temp;
    if (climate.outside_temp != null) categories['Klimaanlage'].outside_temp = climate.outside_temp;
    if (climate.hvac_auto_request != null) categories['Klimaanlage'].hvac_auto_request = climate.hvac_auto_request;
    if (climate.is_climate_on != null) categories['Klimaanlage'].is_climate_on = climate.is_climate_on;
    if (climate.seat_heater_left != null) categories['Klimaanlage'].seat_heater_left = climate.seat_heater_left;
    if (climate.seat_heater_right != null) categories['Klimaanlage'].seat_heater_right = climate.seat_heater_right;

    // Fahrstatus
    if (drive.shift_state != null) categories['Fahrstatus'].shift_state = drive.shift_state;
    if (drive.speed != null) categories['Fahrstatus'].speed = Math.round(drive.speed * MILES_TO_KM);
    if (drive.heading != null) categories['Fahrstatus'].heading = drive.heading;
    if (drive.latitude != null) categories['Fahrstatus'].latitude = drive.latitude;
    if (drive.longitude != null) categories['Fahrstatus'].longitude = drive.longitude;
    if (drive.power != null) categories['Fahrstatus'].power = drive.power;

    // Fahrzeugstatus
    if (vehicle.locked != null) categories['Fahrzeugstatus'].locked = vehicle.locked;
    if (vehicle.odometer != null) categories['Fahrzeugstatus'].odometer = Math.round(vehicle.odometer * MILES_TO_KM);
    if (vehicle.autopark_state_v2 != null) categories['Fahrzeugstatus'].autopark_state_v2 = vehicle.autopark_state_v2;
    if (vehicle.autopark_style != null) categories['Fahrzeugstatus'].autopark_style = vehicle.autopark_style;
    if (vehicle.last_autopark_error != null) categories['Fahrzeugstatus'].last_autopark_error = vehicle.last_autopark_error;
    if (vehicle.software_update && vehicle.software_update.version) categories['Fahrzeugstatus'].software_update = { version: vehicle.software_update.version };
    if (vehicle.speed_limit_mode && vehicle.speed_limit_mode.active != null) categories['Fahrzeugstatus'].speed_limit_mode = { active: vehicle.speed_limit_mode.active };
    if (vehicle.remote_start_enabled != null) categories['Fahrzeugstatus'].remote_start_enabled = vehicle.remote_start_enabled;
    if (vehicle.tpms_pressure_fl != null) categories['Fahrzeugstatus'].tpms_pressure_fl = vehicle.tpms_pressure_fl;
    if (vehicle.tpms_pressure_fr != null) categories['Fahrzeugstatus'].tpms_pressure_fr = vehicle.tpms_pressure_fr;
    if (vehicle.tpms_pressure_rl != null) categories['Fahrzeugstatus'].tpms_pressure_rl = vehicle.tpms_pressure_rl;
    if (vehicle.tpms_pressure_rr != null) categories['Fahrzeugstatus'].tpms_pressure_rr = vehicle.tpms_pressure_rr;

    // Medieninfos
    if (vehicle.media_info) {
        if (vehicle.media_info.media_playback_status != null) categories['Medieninfos'].media_playback_status = vehicle.media_info.media_playback_status;
        if (vehicle.media_info.now_playing_source != null) categories['Medieninfos'].now_playing_source = vehicle.media_info.now_playing_source;
        if (vehicle.media_info.audio_volume != null) categories['Medieninfos'].audio_volume = vehicle.media_info.audio_volume;
    }

    return categories;
}

function generateCategoryTables(cats, status) {
    var html = '';
    var allowed = [];
    if (status === 'Ladevorgang') {
        allowed = ['Batterie und Laden', 'Klimaanlage', 'Fahrzeugstatus', 'Medieninfos'];
    } else if (status === 'Fahrt') {
        allowed = ['Batterie und Laden', 'Fahrstatus', 'Fahrzeugstatus', 'Medieninfos'];
    } else {
        allowed = ['Batterie und Laden', 'Fahrzeugstatus', 'Klimaanlage', 'Medieninfos'];
    }
    Object.keys(cats).forEach(function(name) {
        if (allowed.indexOf(name) === -1) return;
        var obj = cats[name];
        if (Object.keys(obj).length === 0) return;
        html += '<h3>' + name + '</h3>' + generateTable(obj);
    });
    return html;
}

function simpleData(data) {
    var drive = data.drive_state || {};
    var charge = data.charge_state || {};
    var climate = data.climate_state || {};
    var vehicle = data.vehicle_state || {};
    var result = {};

    if (charge.charging_state === 'Charging') {
        if (charge.battery_level != null) result.battery_level = charge.battery_level;
        if (charge.battery_range != null) result.battery_range = (charge.battery_range * MILES_TO_KM).toFixed(1);
        if (charge.charge_rate != null) result.charge_rate = (charge.charge_rate * MILES_TO_KM).toFixed(1);
        if (charge.charger_power != null) result.charger_power = charge.charger_power;
        if (charge.time_to_full_charge != null) result.time_to_full_charge = charge.time_to_full_charge;
    } else if (drive.shift_state && drive.shift_state !== 'P') {
        if (drive.speed != null) result.speed = Math.round(drive.speed * MILES_TO_KM);
        if (drive.heading != null) result.heading = drive.heading;
        if (drive.active_route_miles_to_arrival != null) result.distance_to_arrival = (drive.active_route_miles_to_arrival * MILES_TO_KM).toFixed(1);
        if (charge.battery_level != null) result.battery_level = charge.battery_level;
        if (charge.battery_range != null) result.battery_range = (charge.battery_range * MILES_TO_KM).toFixed(1);
        if (climate.outside_temp != null) result.outside_temp = climate.outside_temp;
    } else {
        if (charge.battery_level != null) result.battery_level = charge.battery_level;
        if (charge.battery_range != null) result.battery_range = (charge.battery_range * MILES_TO_KM).toFixed(1);
        if (vehicle.odometer != null) result.odometer = Math.round(vehicle.odometer * MILES_TO_KM);
        if (vehicle.tpms_pressure_fl != null) result.tpms_pressure_fl = vehicle.tpms_pressure_fl;
        if (vehicle.tpms_pressure_fr != null) result.tpms_pressure_fr = vehicle.tpms_pressure_fr;
        if (vehicle.tpms_pressure_rl != null) result.tpms_pressure_rl = vehicle.tpms_pressure_rl;
        if (vehicle.tpms_pressure_rr != null) result.tpms_pressure_rr = vehicle.tpms_pressure_rr;
        if (drive.power != null) result.power = drive.power;
        var auxPower = null;
        if (vehicle.aux_battery_power != null) {
            auxPower = vehicle.aux_battery_power;
        } else if (vehicle.aux_battery_voltage != null && vehicle.aux_battery_current != null) {
            auxPower = Math.round(vehicle.aux_battery_voltage * vehicle.aux_battery_current);
        }
        if (auxPower != null) result.aux_battery_power = auxPower;
    }

    return result;
}

function updateUI(data) {
    var drive = data.drive_state || {};
    var charge = data.charge_state || {};
    var html = '';
    var status = '';
    parkStart = data.park_start || null;
    if (charge.charging_state === 'Charging') {
        status = 'Ladevorgang';
    } else if (drive.shift_state === 'P' || !drive.shift_state) {
        status = 'Geparkt';
    } else {
        status = 'Fahrt';
    }
    html += '<h2>' + status + '</h2>';
    if (status === 'Geparkt' && parkStart) {
        html += '<p>Geparkt seit <span id="park-time"></span></p>';
        updateParkTime();
        if (!parkTimer) {
            parkTimer = setInterval(updateParkTime, 60000);
        }
    } else {
        if (parkTimer) {
            clearInterval(parkTimer);
            parkTimer = null;
        }
    }
    html += generateTable(simpleData(data));
    html += generateCategoryTables(categorizedData(data), status);
    $('#info').html(html);
}

$('#vehicle-select').on('change', function() {
    currentVehicle = $(this).val();
    fetchData();
});

fetchVehicles();
setInterval(fetchData, 5000);
