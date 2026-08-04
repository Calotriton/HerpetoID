---
layout: page
title: News
subtitle: Releases, new species modules, and project updates.
permalink: /news/
description: Announcements about HerpetoID releases, new species modules and matching algorithms.
---

<p class="muted">
  Follow along by <a href="{{ '/feed.xml' | relative_url }}">RSS</a>, or
  <a href="{{ site.github_repo_url }}" rel="noopener">watch the repository</a> to be notified of every release.
</p>

<ul class="post-list">
  {%- for post in site.posts %}
  <li>
    <p class="post-meta">
      <time datetime="{{ post.date | date_to_xmlschema }}">{{ post.date | date: "%-d %B %Y" }}</time>
      {%- if post.tag %}<span class="tag">{{ post.tag }}</span>{% endif %}
    </p>
    <h2><a href="{{ post.url | relative_url }}">{{ post.title }}</a></h2>
    <p>{{ post.excerpt | strip_html | truncate: 200 }}</p>
  </li>
  {%- else %}
  <li><p>No posts yet.</p></li>
  {%- endfor %}
</ul>
