    function aggregateMatchData(docs) {
        // Aggregates raw match data by docid for display
        var quoteIDs = {};
        var byDocid = {};
        var matchSeq = 0;
        for (var i = 0; i < docs.length; i++) {
            var rawMatch = docs[i];
            matchSeq += 1;
            if (!(rawMatch.docid in byDocid)) {
                var split = rawMatch.docid.split('/');
                byDocid[rawMatch.docid] = {
                    docid:     rawMatch.docid,
                    stableURL: 'http://www.jstor.org/stable/' + ((split.length == 1 || split[0] == '10.2307') ? split[split.length-1] : rawMatch.docid),
                    journal:   rawMatch.journal,
                    title:     rawMatch.title,
                    authors:   rawMatch.authors ? rawMatch.authors.join(', ') : '',
                    pubyear:   rawMatch.pubyear,
                    keyterms:  rawMatch.keyterms ? rawMatch.keyterms.join(' | ') : '',
                    topics:    rawMatch.topics ? rawMatch.topics.join(' | ') : '',
                    explain:   rawMatch.explain,
                    matches:  []
                };
                matchSeq = 0;
            }
            if (!(rawMatch.quote_id in quoteIDs)) {
                var smallSnippet = rawMatch.match_prefix.slice(rawMatch.match_prefix.length - 100, rawMatch.match_prefix.length) +
                    '<em>' + rawMatch.match_exact + '</em>' + rawMatch.match_suffix.slice(0, 100);
                smallSnippet = smallSnippet.replace('- ', '');
                var match = {
                    matchid: rawMatch.docid.replace('/', '|') + '|' + rawMatch.pages[0] + '|' + matchSeq,
                    score: rawMatch.score,
                    work: rawMatch.work,
                    chunk_ids: rawMatch.chunk_ids,
                    similarity: rawMatch.similarity,
                    match_size: rawMatch.match_size,
                    work_text: rawMatch.work_text,
                    regions: [],
                    snippet: {
                        page: rawMatch.pages[0],
                        exact: rawMatch.match_exact,
                        text: rawMatch.snippet,
                        prefix: rawMatch.match_prefix,
                        suffix: rawMatch.match_suffix,
                        small: smallSnippet,
                        similarity: rawMatch.similarity,
                        size: rawMatch.match_size,
                        source: rawMatch.source
                    },
                }
                if (rawMatch.regions) {
                    for (var r = 0; r < rawMatch.regions.length; r++) {
                        var s = rawMatch.regions[r].split(' ');
                        match.regions.push({
                            page: parseInt(s[0]),
                            ratio: parseFloat(s[1]),
                            left: parseFloat(s[2]),
                            width: parseFloat(s[3]),
                            top: parseFloat(s[4]),
                            height: parseFloat(s[5])
                        });
                    }
                }
                byDocid[rawMatch.docid]['matches'].push(match);
                quoteIDs[rawMatch.quote_id] = true;
            }
        }

        var aggregated = [];
        for (var docid in byDocid) {
            aggregated.push(byDocid[docid]);
        }
        //aggregated.sort(function (a, b) {
            //return b.matches[0].similarity*b.matches[0].match_size - a.matches[0].similarity*a.matches[0].match_size;
            //return b.matches[0].similarity - a.matches[0].similarity;
            //return b.pubyear - a.pubyear;
            //return b.matches[0].score - a.matches[0].score;
        //});
        return aggregated;
    }