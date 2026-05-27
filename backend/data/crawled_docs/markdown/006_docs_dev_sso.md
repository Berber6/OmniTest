# SSO (Single sign-on) | 4ga Boards Docs

Source: https://docs.4gaboards.com/docs/dev/sso

# SSO (Single sign-on)
### Google SSO[​](https://docs.4gaboards.com/docs/dev/sso/#google-sso "Direct link to Google SSO")
Create a project on   
Create OAuth 2.0 Client ID and Client Secret.  
Configure 4ga Boards instance variables in the appropriate config file _(check your install method docs for details)_ - set Client ID and Client Secret to `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` to the values from the Google Cloud Console.

```


GOOGLE_CLIENT_ID: googleClientId  


GOOGLE_CLIENT_SECRET: googleClientSecret  


```

### GitHub SSO[​](https://docs.4gaboards.com/docs/dev/sso/#github-sso "Direct link to GitHub SSO")
Create an app on GitHub:   
Create OAuth 2.0 Client ID and Client Secret.  
Configure 4ga Boards instance variables in the appropriate config file _(check your install method docs for details)_ - set Client ID and Client Secret to `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` to the values from the GitHub App.

```


GITHUB_CLIENT_ID: githubClientId  


GITHUB_CLIENT_SECRET: githubClientSecret  


```

### Microsoft SSO[​](https://docs.4gaboards.com/docs/dev/sso/#microsoft-sso "Direct link to Microsoft SSO")
Create an app on   
Create OIDC Client ID and Client Secret.  
Configure 4ga Boards instance variables in the appropriate config file _(check your install method docs for details)_ - set Client ID and Client Secret to `MICROSOFT_CLIENT_ID` and `MICROSOFT_CLIENT_SECRET` to the values from the Entra App.

```


MICROSOFT_CLIENT_ID: microsoftClientId  


MICROSOFT_CLIENT_SECRET: microsoftClientSecret  


```

### OIDC SSO[​](https://docs.4gaboards.com/docs/dev/sso/#oidc-sso "Direct link to OIDC SSO")
Create an app on OIDC provider website.  
Create OIDC Client ID and Client Secret.  
Configure 4ga Boards instance variables in the appropriate config file _(check your install method docs for details)_ - set Client ID and Client Secret to `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` to the values from the app.

```


OIDC_CLIENT_ID: oidcClientId  


OIDC_CLIENT_SECRET: oidcClientSecret  


OIDC_ISSUER_URL: https://oidcIssuer.com  


OIDC_STATE_SECRET: stateSecret  


```

`REDIRECT_URL` that you should use to get back to 4ga Boards instance after authentication by OIDC provider is e.g. `https://instance.domain.com/auth/oidc/callback"`