# Factcheck Ranges — client-side review verification

The swarm embeds `<script id=factcheck type=application/json>{json}</script>` per lesson.
`factcheck_json(title)` picks entries whose keyword is in the title. `site.js` parses
posted review text for numbers + units and compares to {min,max,unit,label}. Status:
accept (in range) / flag (out of range) / note (no numeric claim).

Keyword -> field -> {min, max, unit, label}:
```
anfo        : AN_FO_ratio {90,97,%,"AN:FO mass %"}
            : density     {0.7,0.95,g/cc,"loaded density"}
            : vod         {3.8,5.0,km/s,"detonation velocity"}
thermite    : ratio       {2.5,4.0,,"Fe2O3:Al mass ratio"}
            : temp        {2000,3000,°,"flame temp C"}
etn         : ratio       {6,10,,"HNO3:erythritol molar"}
            : vod         {7.0,8.5,km/s,"detonation velocity"}
            : temp        {0,10,°,"ice-bath temp C"}
shaped charge: standoff   {1,4,,"standoff in cone diameters"}
            : cone        {55,65,°,"cone half-apex"}
rtlsdr      : low         {20,30,MHz,"low tune"}
            : high        {1.5,2.0,GHz,"high tune"}
geiger      : temp        {-20,50,°,"operating temp"}
ferment     : salt        {1.5,4.0,%,"salt brine %"}
            : ph          {3.5,4.5,,"final pH"}
faraday     : gap         {0,5,mm,"seam gap"}
```
Expand this table as new subjects get real data; the review fact-check only works for
keywords present here (otherwise it returns a "note" with no automated check).
